"""Zscaler の E2E の共通処理（ホストの pytest から docker の CLI でコンテナを操作する）。"""

import os
import subprocess
from pathlib import Path
from typing import Optional

import pytest

REPO = Path(__file__).resolve().parents[2]
ZSCALER_DIR = REPO / ".zscaler"
MOCK_CONTAINER = "zscaler-mock-zscaler_mock-1"
MOCK_HOST_PROXY = "http://127.0.0.1:18080"
CLI_IMAGES = {
    "claude": "coding-agent-cli-exec-claude:latest",
    "opencode": "coding-agent-cli-exec-opencode:latest",
}
HOST_BUNDLE_CANDIDATES = ["/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt", "/etc/ssl/cert.pem"]


def run(cmd: list[str], timeout: int = 600, env: Optional[dict] = None, check: bool = False) -> subprocess.CompletedProcess:
    """コマンドを実行して結果を返す。"""
    merged = {**os.environ, **(env or {})}
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=merged, cwd=REPO)
    if check and result.returncode != 0:
        raise AssertionError(f"失敗: {' '.join(cmd)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")
    return result


def zscaler_state() -> str:
    """生成物の状態（enabled / disabled / 無し）を返す。"""
    state = ZSCALER_DIR / "state"
    return state.read_text().strip() if state.exists() else ""


def mock_running() -> bool:
    """模擬プロキシが動いているかを返す。"""
    result = run(["docker", "inspect", "-f", "{{.State.Running}}", MOCK_CONTAINER], timeout=30)
    return result.returncode == 0 and result.stdout.strip() == "true"


def mock_log(since: Optional[str] = None) -> str:
    """模擬プロキシの通信の記録を返す。"""
    cmd = ["docker", "logs", MOCK_CONTAINER]
    if since:
        cmd[2:2] = ["--since", since]
    result = run(cmd, timeout=60)
    return result.stdout + result.stderr


def host_bundle() -> str:
    """ホストの OS の証明書の束のパスを返す。"""
    for candidate in HOST_BUNDLE_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    pytest.skip("ホストの OS の証明書の束が見つかりません")


def run_cli_image(image: str, script: str, timeout: int = 900, privileged: bool = False) -> subprocess.CompletedProcess:
    """CLI コンテナのイメージで、Zscaler 設定の環境変数を渡してスクリプトを実行する（起動処理を通す）。"""
    cmd = ["docker", "run", "--rm", "--env-file", str(ZSCALER_DIR / "zscaler.env"),
           "--add-host", "host.docker.internal:host-gateway"]
    if privileged:
        cmd.append("--privileged")
    cmd += [image, "bash", "-c", script]
    return run(cmd, timeout=timeout)


requires_mock = pytest.mark.skipif(
    not (zscaler_state() == "enabled" and mock_running()),
    reason="模擬プロキシ付きのセットアップ（./scripts/test_setup.sh --zscaler-mock）でだけ確かめる",
)
requires_disabled = pytest.mark.skipif(
    zscaler_state() != "disabled",
    reason="Zscaler 設定を無効にしたセットアップでだけ確かめる",
)
