"""実行時の設定の E2E（GitLab の URL、テスト環境の構築の冪等性、LiteLLM Proxy への呼び出し）。

`./scripts/test_setup.sh --run-tests` のステップ 8 から、Zscaler の E2E と一緒に実行する。
構築の最初の `.env` のハッシュ、Playwright の E2E を始めた時刻、LiteLLM Proxy のサービス名は、
test_setup.sh が環境変数で渡す。渡されていないとき（単独で実行したとき）は、それを使うテストを飛ばす。
"""

import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest

from conftest import REPO, run

# 本番の状態として .env に書く、テスト用の GitLab と違う URL
_PRODUCTION_GITLAB_URL = "https://gitlab.example.invalid"
# テスト環境の構築が .env.test に書く、コンテナから見たテスト用の GitLab の URL
_CONTAINER_GITLAB_URL = "http://gitlab:8929"
# LiteLLM Proxy が、自分に無いモデルの呼び出しを断ったときにログへ残す文言
_UNKNOWN_MODEL_MARK = "Invalid model name passed in model="
_GITLAB_URL_SERVICES = ("producer", "consumer")
_TEST_SERVICES = ("test_playwright", "test_playwright_real")


def _expand_compose(project_dir: Path) -> dict:
    """一時ディレクトリの compose の構成を展開して返す（起動はしない）。"""
    result = run(
        ["docker", "compose", "--project-directory", str(project_dir), "-f", str(project_dir / "docker-compose.yml"),
         "--profile", "test", "--profile", "test-real", "config", "--format", "json"],
        timeout=120, check=True,
    )
    return json.loads(result.stdout)["services"]


def _env_value(path: Path, key: str) -> str:
    """KEY=VALUE 形式のファイルから、指定したキーの値を返す（無ければ空文字）。"""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip('"')
    return ""


def test_gitlab_url_from_env(tmp_path: Path) -> None:
    """本番の状態では .env の GitLab の URL が、テスト環境では .env.test の URL が producer と consumer に渡ること。"""
    shutil.copy(REPO / "docker-compose.yml", tmp_path / "docker-compose.yml")
    (tmp_path / ".env").write_text(f"GITLAB_API_URL={_PRODUCTION_GITLAB_URL}\n", encoding="utf-8")
    (tmp_path / ".zscaler").mkdir()
    (tmp_path / ".zscaler" / "zscaler.env").write_text("", encoding="utf-8")

    # 本番の状態（.env.test が無い）
    services = _expand_compose(tmp_path)
    for name in _GITLAB_URL_SERVICES:
        assert services[name]["environment"]["GITLAB_API_URL"] == _PRODUCTION_GITLAB_URL, name
    for name in _TEST_SERVICES:
        assert "GITLAB_API_URL" not in services[name].get("environment", {}), name

    # テスト環境（.env.test がある）
    (tmp_path / ".env.test").write_text(f"GITLAB_API_URL={_CONTAINER_GITLAB_URL}\n", encoding="utf-8")
    services = _expand_compose(tmp_path)
    for name in _GITLAB_URL_SERVICES + _TEST_SERVICES:
        assert services[name]["environment"]["GITLAB_API_URL"] == _CONTAINER_GITLAB_URL, name


@pytest.mark.skipif(not os.environ.get("E2E_ENV_FILE_HASH"), reason="test_setup.sh から実行したときだけ確かめる")
def test_test_setup_repeatable() -> None:
    """テスト環境の構築が .env を書き換えず、.env.test にコンテナから見た GitLab の URL を書くこと。"""
    env_hash = hashlib.sha256((REPO / ".env").read_bytes()).hexdigest()
    assert env_hash == os.environ["E2E_ENV_FILE_HASH"], "テスト環境の構築が .env を書き換えた"
    assert _env_value(REPO / ".env.test", "GITLAB_API_URL") == _CONTAINER_GITLAB_URL


@pytest.mark.skipif(not os.environ.get("E2E_STARTED_AT"), reason="test_setup.sh から実行したときだけ確かめる")
def test_opencode_no_unknown_model_call() -> None:
    """Playwright の E2E の間に、LiteLLM Proxy に無いモデルの呼び出しが 0 件であること。"""
    service = os.environ.get("E2E_LITELLM_SERVICE", "litellm")
    result = run(
        ["docker", "compose", "--profile", "test", "--profile", "test-real",
         "logs", "--no-color", "--since", os.environ["E2E_STARTED_AT"], service],
        timeout=120, check=True,
    )
    unknown = [line for line in (result.stdout + result.stderr).splitlines() if _UNKNOWN_MODEL_MARK in line]
    assert not unknown, "LiteLLM Proxy に無いモデルの呼び出しがありました:\n" + "\n".join(unknown[:20])
