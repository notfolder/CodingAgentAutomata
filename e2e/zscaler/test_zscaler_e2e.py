"""Zscaler 環境対応の E2E。

`./scripts/test_setup.sh --zscaler-mock --run-tests`（模擬プロキシ）と
`ZSCALER_ENABLED=false ./scripts/test_setup.sh --run-tests`（無効）から実行する。
"""

import hashlib
import json
import os
import shutil
import time
from pathlib import Path

import pytest

from conftest import (
    CLI_IMAGES,
    MOCK_HOST_PROXY,
    REPO,
    ZSCALER_DIR,
    host_bundle,
    mock_log,
    requires_disabled,
    requires_mock,
    run,
    run_cli_image,
)

_PROBE_URL = "https://pypi.org/simple/pip/"
# ブラウザを取得した直後は、コンテナの実行環境によって外への最初の接続が数十秒詰まることがある
# （OrbStack で確認。公式の Playwright イメージでも同じ）。そのため 1 回 60 秒まで、3 回まで試す。
# 失敗したページはエラーページへ移るので、試すたびに新しいページを開く。
_BROWSER_SCRIPT = (
    "const { chromium, webkit } = require('playwright');"
    "const open = async (b, n) => { for (let i = 1; ; i++) { const p = await b.newPage();"
    " try { await p.goto('https://example.com/', { timeout: 60000 }); return p; }"
    " catch (e) { await p.close(); if (i >= 3) throw e;"
    " console.error('RETRY:' + n + ':' + i + ':' + e.message.split(String.fromCharCode(10))[0]);"
    " await new Promise(r => setTimeout(r, 5000)); } } };"
    "(async () => { for (const t of [chromium, webkit]) {"
    " const b = await t.launch(); const p = await open(b, t.name());"
    " console.log('TITLE:' + t.name() + ':' + await p.title());"
    " await b.close(); } })().catch(e => { console.error(e); process.exit(1); });"
)


def _browser_check(image: str) -> str:
    """CLI を実行する利用者として、標準の Chromium と WebKit を取得して外部のサイトを開く。"""
    script = (
        "set -e; export NODE_PATH=$(npm root -g); cd /tmp;"
        " npx playwright install chromium webkit >/tmp/install.log 2>&1 || { tail -20 /tmp/install.log; exit 1; };"
        f" node -e \"{_BROWSER_SCRIPT}\""
    )
    result = run_cli_image(image, script, timeout=1800)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


# ---- 模擬プロキシ経由のシナリオ ----------------------------------------------


@requires_mock
def test_build_via_zscaler_mock() -> None:
    """全イメージのビルドの通信が模擬プロキシを経由したこと。"""
    log = mock_log()
    for host in ["pypi.org", "files.pythonhosted.org", "registry.npmjs.org", "download.docker.com", "deb.nodesource.com", "astral.sh"]:
        assert host in log, f"{host} のビルドの通信が模擬プロキシに記録されていません"


@requires_mock
def test_runtime_https_via_zscaler_mock() -> None:
    """実行中の各部品から、模擬プロキシ経由で証明書を検証して HTTPS につなげること。"""
    since = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 5))
    for service in ["backend", "producer", "consumer"]:
        run(["docker", "compose", "exec", "-T", service, "python", "-c",
             f"import requests; requests.get('{_PROBE_URL}', timeout=30).raise_for_status()"], check=True)
    run(["docker", "compose", "exec", "-T", "backend", "python", "-c",
         f"import httpx; httpx.get('{_PROBE_URL}', timeout=30).raise_for_status()"], check=True)
    script = (
        "set -e;"
        f" NODE_USE_ENV_PROXY=1 node -e \"fetch('{_PROBE_URL}').then(r => process.exit(r.ok ? 0 : 1))\";"
        f" curl -fsS -o /dev/null {_PROBE_URL};"
        " git ls-remote https://github.com/git/git HEAD >/dev/null;"
        " uv venv -q /tmp/v && uv pip install -q --python /tmp/v/bin/python requests;"
        " python3 -m pip download -q --no-deps -d /tmp/p requests;"
        " curl -sS -o /dev/null https://api.anthropic.com/"
    )
    for image in CLI_IMAGES.values():
        result = run_cli_image(image, script)
        assert result.returncode == 0, f"{image}: {result.stdout}{result.stderr}"
    log = mock_log(since)
    for host in ["pypi.org", "github.com", "api.anthropic.com"]:
        assert host in log


@requires_mock
def test_untrusted_cert_stops(tmp_path: Path) -> None:
    """模擬の認証局を含まない束では、使用前の接続確認が止めること。"""
    (tmp_path / ".env").write_text(f"ZSCALER_PROXY_URL={MOCK_HOST_PROXY}\n")
    result = run(["bash", "scripts/zscaler_prepare.sh", "--project-dir", str(tmp_path), "--host-bundle", host_bundle()],
                 env={"ZSCALER_ENABLED": "", "ZSCALER_PROXY_URL": ""})
    assert result.returncode == 1
    assert "証明書を検証できない" in result.stderr
    assert not (tmp_path / ".zscaler").exists()


@requires_mock
def test_os_bundle_fallback(tmp_path: Path) -> None:
    """証明書ファイルが無いとき、ホストの OS の束を使うこと。"""
    bundle = tmp_path / "os-bundle.pem"
    bundle.write_text(Path(host_bundle()).read_text() + (REPO / "zscaler-mock/.data/mitmproxy-ca-cert.pem").read_text())
    (tmp_path / ".env").write_text(f"ZSCALER_PROXY_URL={MOCK_HOST_PROXY}\n")
    result = run(["bash", "scripts/zscaler_prepare.sh", "--project-dir", str(tmp_path), "--host-bundle", str(bundle)],
                 env={"ZSCALER_ENABLED": "", "ZSCALER_PROXY_URL": ""})
    assert result.returncode == 0, result.stderr
    assert (tmp_path / ".zscaler/extra-ca.pem").read_text() == bundle.read_text()
    assert (tmp_path / ".zscaler/ca-bundle.pem").read_text() == bundle.read_text()


@requires_mock
def test_mock_llm_e2e_internal_traffic_not_proxied() -> None:
    """部品どうしの通信が模擬プロキシを経由せず、compose の全サービス名が除外宛先に入っていること。"""
    services = run(["docker", "compose", "--profile", "test", "--profile", "test-real", "--profile", "build-only",
                    "config", "--services"], check=True).stdout.split()
    no_proxy = (ZSCALER_DIR / "zscaler.env").read_text().split("NO_PROXY=")[1].splitlines()[0].split(",")
    missing = [s for s in services if s not in no_proxy]
    assert missing == []
    log = mock_log()
    for internal in ["backend:8000", "gitlab:8929", "mock_llm:4000", "litellm:4000", "rabbitmq:5672"]:
        assert internal not in log


@requires_mock
@pytest.mark.skipif(os.environ.get("E2E_REAL_LLM") != "true", reason="実 LLM モード（--real）でだけ確かめる")
def test_real_llm_traffic_via_mock() -> None:
    """実 LLM モードで、LLM の API への通信が模擬プロキシを経由したこと。"""
    log = mock_log()
    assert "api.anthropic.com" in log or "api.openai.com" in log


@requires_mock
def test_cli_zscaler_instruction_and_inner_proxy() -> None:
    """指示文がプロンプトに付き、CLI コンテナの中のコンテナに宛先が渡ること。"""
    code = (
        "from shared.database.database import SessionLocal;"
        "from consumer.prompt_builder import PromptBuilder;"
        "from consumer.zscaler_settings import ZscalerSettings;"
        "s = ZscalerSettings.from_env(); b = PromptBuilder(SessionLocal, s); i = s.build_instruction();"
        "assert i;"
        "assert b.build_f3_prompt('t', 'd', 'c', 'p', 'r', 'b').endswith(i);"
        "assert b.build_f4_prompt('d', 'c', 'b', 'r').endswith(i);"
        "assert b.build_f4_prompt('d', 'c', 'b', 'r', user_f4_template='個別 {mr_description}').endswith(i)"
    )
    run(["docker", "compose", "exec", "-T", "consumer", "python", "-c", code], check=True)
    since = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 5))
    script = (
        "for i in $(seq 1 60); do docker info >/dev/null 2>&1 && break; sleep 2; done;"
        " docker run --rm alpine:3.20 env;"
        f" docker run --rm alpine:3.20 sh -c 'wget -q -O /dev/null {_PROBE_URL} || true'"
    )
    result = run_cli_image(CLI_IMAGES["opencode"], script, privileged=True)
    assert result.returncode == 0, result.stdout + result.stderr
    env_lines = result.stdout.splitlines()
    proxy = [line for line in env_lines if line.startswith("HTTPS_PROXY=")]
    assert proxy and "host.docker.internal" not in proxy[0], proxy
    assert any(line.startswith("NO_PROXY=") and "backend" in line for line in env_lines)
    log = mock_log(since)
    assert "pypi.org" in log

    # 指示文が CLI エージェントに伝える場所に、足した証明書と、それを含む OS の束がある
    extra_ca = (ZSCALER_DIR / "extra-ca.pem").read_text()
    cert_hash = hashlib.sha256(extra_ca.encode()).hexdigest()
    body_line = next(line for line in extra_ca.splitlines() if line and not line.startswith("-----"))
    for image in CLI_IMAGES.values():
        check = (
            "sha256sum /usr/local/share/ca-certificates/zscaler.crt | cut -d' ' -f1;"
            f" grep -cF '{body_line}' /etc/ssl/certs/ca-certificates.crt"
        )
        out = run_cli_image(image, check)
        assert out.returncode == 0, out.stdout + out.stderr
        lines = out.stdout.split()
        assert lines[0] == cert_hash, (image, lines)
        assert int(lines[1]) >= 1, (image, lines)


@requires_mock
@pytest.mark.parametrize("name", list(CLI_IMAGES))
def test_cli_browser_trust(name: str) -> None:
    """CLI コンテナの Chromium と WebKit が、模擬プロキシ経由で証明書を検証して外部のサイトを開けること。"""
    since = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 5))
    out = _browser_check(CLI_IMAGES[name])
    assert "TITLE:chromium:Example Domain" in out
    assert "TITLE:webkit:Example Domain" in out
    assert "example.com" in mock_log(since)


@requires_mock
def test_real_settings_unchanged() -> None:
    """模擬プロキシの準備が、本物の証明書ファイルと .env を書き換えないこと。"""
    cert = REPO / "certs" / "zscaler-ca.pem"
    created = False
    if not cert.exists():
        cert.parent.mkdir(exist_ok=True)
        cert.write_text("-----BEGIN CERTIFICATE-----\nZHVtbXk=\n-----END CERTIFICATE-----\n")
        created = True
    try:
        env = REPO / ".env"
        before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in (cert, env)]
        run(["bash", "scripts/zscaler_prepare.sh", "--mock"], check=True)
        after = [hashlib.sha256(p.read_bytes()).hexdigest() for p in (cert, env)]
        assert before == after
    finally:
        if created:
            cert.unlink()
            if not any(cert.parent.iterdir()):
                shutil.rmtree(cert.parent)


# ---- どちらの状態でも確かめるシナリオ ------------------------------------------


def test_missing_settings_stop(tmp_path: Path) -> None:
    """設定の不足で、準備処理と compose の入口スクリプトが止まること。"""
    (tmp_path / ".env").write_text("ZSCALER_PROXY_URL=\n")
    result = run(["bash", "scripts/zscaler_prepare.sh", "--project-dir", str(tmp_path), "--host-bundle", host_bundle()],
                 env={"ZSCALER_ENABLED": "", "ZSCALER_PROXY_URL": ""})
    assert result.returncode == 1
    assert "ZSCALER_PROXY_URL" in result.stderr and "ZSCALER_ENABLED=false" in result.stderr
    before = (ZSCALER_DIR / "state").read_text()
    result = run(["bash", "scripts/compose.sh", "build", "backend"],
                 env={"ZSCALER_ENABLED": "true", "ZSCALER_PROXY_URL": "not-a-url", "ZSCALER_PREPARED": ""})
    assert result.returncode == 1
    assert "ZSCALER_PROXY_URL" in result.stderr and "ZSCALER_ENABLED=false" in result.stderr
    assert "Building" not in result.stdout + result.stderr
    assert (ZSCALER_DIR / "state").read_text() == before


def test_local_image_names() -> None:
    """compose がビルドするイメージの名前に、外部のレジストリの名前が入っていないこと。"""
    config = json.loads(run(["docker", "compose", "--profile", "test", "--profile", "test-real", "--profile", "build-only",
                             "config", "--format", "json"], check=True).stdout)
    built = {name: svc.get("image", "") for name, svc in config["services"].items() if "build" in svc}
    assert built
    for name, image in built.items():
        first = image.split("/")[0]
        assert "/" not in image or ("." not in first and ":" not in first), f"{name}: {image}"


# ---- Zscaler 設定を無効にしたときのシナリオ ----------------------------------


@requires_disabled
def test_disabled_switch() -> None:
    """無効なとき、consumer が CLI へ指示文もプロキシも渡さないこと。"""
    code = (
        "from consumer.zscaler_settings import ZscalerSettings;"
        "s = ZscalerSettings.from_env();"
        "assert s.enabled is False and s.build_instruction() == '';"
        "assert s.build_cli_env() == {'ZSCALER_ENABLED': 'false'}"
    )
    run(["docker", "compose", "exec", "-T", "consumer", "python", "-c", code], check=True)


@requires_disabled
@pytest.mark.parametrize("name", list(CLI_IMAGES))
def test_cli_standard_browsers(name: str) -> None:
    """CLI コンテナで、Playwright の標準の Chromium と WebKit が起動してページを開けること。"""
    out = _browser_check(CLI_IMAGES[name])
    assert "TITLE:chromium:Example Domain" in out
    assert "TITLE:webkit:Example Domain" in out
