"""Zscaler 設定の準備処理（scripts/lib/zscaler.sh・scripts/zscaler_prepare.sh）の単体・結合テスト。

ネットワークを使わない判定と生成物を確かめる（使用前の接続確認は E2E で確かめる）。
"""

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PREPARE = REPO / "scripts" / "zscaler_prepare.sh"
CERT = "-----BEGIN CERTIFICATE-----\nMIIBfake\n-----END CERTIFICATE-----\n"


def _bash(script: str) -> subprocess.CompletedProcess:
    """共通処理を読み込んだ bash でスクリプトを実行する。"""
    return subprocess.run(
        ["bash", "-c", f"source '{REPO}/scripts/lib/env.sh'; source '{REPO}/scripts/lib/zscaler.sh'; {script}"],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/local/bin:/usr/bin:/bin"},
    )


def _prepare(project: Path, *args: str) -> subprocess.CompletedProcess:
    """準備処理のコマンドを実行する。"""
    return subprocess.run(
        ["bash", str(PREPARE), "--project-dir", str(project), *args],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/local/bin:/usr/bin:/bin"},
    )


def test_load_env_file_and_read_env_value(tmp_path: Path) -> None:
    """コメント・空行・引用符・CR を扱い、同じ項目は最後の値を返すこと。"""
    env = tmp_path / ".env"
    env.write_text('# c\n\nA="x y"\r\nB=1\nB=2\n')
    out = _bash(f"load_env_file '{env}'; echo \"$A|$B\"; read_env_value '{env}' B; echo; read_env_value '{env}' Z; echo end")
    assert out.stdout.splitlines() == ["x y|2", "2", "end"]


def test_no_proxy_includes_services_and_extra() -> None:
    """除外宛先に本システムの部品の名前と社内の宛先が入り、重複と空白が除かれること。"""
    out = _bash('zscaler_build_no_proxy " corp.example , gitlab.corp,localhost,,"').stdout.split(",")
    for name in ["localhost", "127.0.0.1", "backend", "consumer", "litellm", "gitlab", "corp.example", "gitlab.corp"]:
        assert name in out
    assert out.count("localhost") == 1
    assert "" not in out


def test_require_settings_messages() -> None:
    """不正な値・宛先の不足・宛先の形・証明書の不足でそれぞれ止まること。"""
    cases = [
        ("yes http://p:1 /none /etc/hosts", "ZSCALER_ENABLED の値「yes」"),
        ("true '' /none /etc/hosts", "ZSCALER_PROXY_URL がありません"),
        ("true https://p:1 /none /etc/hosts", "形が正しくありません"),
        ("true http://p /none /etc/hosts", "形が正しくありません"),
        ("true http://p:1 /none ''", "Zscaler の証明書がありません"),
    ]
    for args, message in cases:
        out = _bash(f"zscaler_require_settings {args}")
        assert out.returncode == 1, args
        assert message in out.stderr, args
        assert "ZSCALER_ENABLED=false" in out.stderr or "true か false" in out.stderr
    assert _bash("zscaler_require_settings true http://p:8080 /none /etc/hosts").returncode == 0
    assert _bash("zscaler_require_settings false '' /none ''").returncode == 0


def test_prepare_disabled_writes_outputs(tmp_path: Path) -> None:
    """無効なとき、生成物を作り、プロキシを含めないこと。"""
    (tmp_path / ".env").write_text("ZSCALER_ENABLED=false\nZSCALER_PROXY_URL=http://p:1\n")
    bundle = tmp_path / "bundle.pem"
    bundle.write_text(CERT)
    out = _prepare(tmp_path, "--host-bundle", str(bundle))
    assert out.returncode == 0, out.stderr
    gen = tmp_path / ".zscaler"
    assert (gen / "state").read_text().strip() == "disabled"
    assert (gen / "zscaler.env").read_text().strip() == "ZSCALER_ENABLED=false"
    assert (gen / "ca-bundle.pem").read_text() == CERT
    assert "ZSCALER_BUILD_PROXY=\n" in (gen / "build.env").read_text()
    assert (gen / "install-ca.sh").is_file()
    assert not (gen / "extra-ca.pem").exists()


def test_prepare_failure_keeps_previous_outputs(tmp_path: Path) -> None:
    """失敗したとき、終了コード 1 で、前回の生成物を書き換えないこと。"""
    bundle = tmp_path / "bundle.pem"
    bundle.write_text(CERT)
    (tmp_path / ".env").write_text("ZSCALER_ENABLED=false\n")
    assert _prepare(tmp_path, "--host-bundle", str(bundle)).returncode == 0
    (tmp_path / ".env").write_text("ZSCALER_PROXY_URL=\n")
    out = _prepare(tmp_path, "--host-bundle", str(bundle))
    assert out.returncode == 1
    assert "ZSCALER_PROXY_URL" in out.stderr
    assert (tmp_path / ".zscaler" / "state").read_text().strip() == "disabled"
    assert not list(tmp_path.glob(".zscaler.tmp.*"))


def test_prepare_missing_switch_means_enabled(tmp_path: Path) -> None:
    """スイッチを書いていない場合は有効とみなし、宛先が無ければ止まること。"""
    (tmp_path / ".env").write_text("")
    bundle = tmp_path / "bundle.pem"
    bundle.write_text(CERT)
    out = _prepare(tmp_path, "--host-bundle", str(bundle))
    assert out.returncode == 1
    assert "Zscaler 設定が有効ですが" in out.stderr


def test_prepare_mock_requires_mock_ca(tmp_path: Path) -> None:
    """--mock で模擬プロキシの認証局の証明書が無ければ止まること。"""
    out = _prepare(tmp_path, "--mock")
    assert out.returncode == 1
    assert "模擬プロキシの認証局の証明書がありません" in out.stderr


def test_install_ca_states(tmp_path: Path) -> None:
    """導入処理は、無効なら何もせず、準備が無ければ止まり、有効でプロキシが無ければ止まること。"""
    script = REPO / "scripts" / "zscaler" / "install-ca.sh"
    work = tmp_path / "z"
    work.mkdir()
    (work / "install-ca.sh").write_text(script.read_text())
    run = lambda env: subprocess.run(["sh", str(work / "install-ca.sh")], capture_output=True, text=True, env=env)
    base_env = {"PATH": "/usr/bin:/bin"}
    out = run(base_env)
    assert out.returncode == 1 and "準備ができていません" in out.stderr
    (work / "state").write_text("disabled\n")
    assert run(base_env).returncode == 0
    (work / "state").write_text("enabled\n")
    out = run(base_env)
    assert out.returncode == 1 and "プロキシの宛先が渡されていません" in out.stderr
