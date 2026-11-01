"""CLIContainerManager の Zscaler の環境変数と追加のホスト名の単体テスト。"""

from unittest import mock

import docker.errors
import pytest

from consumer import cli_container_manager
from consumer.cli_container_manager import CLIContainerManager
from consumer.zscaler_settings import ZscalerSettings


def _manager(settings: ZscalerSettings) -> tuple[CLIContainerManager, mock.MagicMock]:
    """Docker クライアントを差し替えた CLIContainerManager を作る。"""
    client = mock.MagicMock()
    client.containers.get.side_effect = docker.errors.NotFound("none")
    with mock.patch.object(cli_container_manager.docker, "from_env", return_value=client):
        manager = CLIContainerManager(warmup_images=[], zscaler_settings=settings)
    return manager, client


def test_start_container_adds_proxy_env_and_extra_hosts() -> None:
    """有効なとき、プロキシの環境変数と host.docker.internal を付けてコンテナを作ること。"""
    settings = ZscalerSettings(enabled=True, proxy_url="http://p:8080", no_proxy="localhost")
    manager, client = _manager(settings)
    client.containers.create.return_value = mock.MagicMock(id="cid")
    manager.start_container("cli-exec-x", "img", {"ANTHROPIC_API_KEY": "k"})
    kwargs = client.containers.create.call_args.kwargs
    assert kwargs["environment"]["HTTPS_PROXY"] == "http://p:8080"
    assert kwargs["environment"]["no_proxy"] == "localhost"
    assert kwargs["environment"]["ZSCALER_ENABLED"] == "true"
    assert kwargs["environment"]["ANTHROPIC_API_KEY"] == "k"
    assert kwargs["extra_hosts"] == {"host.docker.internal": "host-gateway"}


def test_run_container_once_passed_env_wins_and_disabled_flag() -> None:
    """渡された環境変数が優先され、無効なときは ZSCALER_ENABLED=false だけが足されること。"""
    manager, client = _manager(ZscalerSettings(enabled=False))
    client.containers.create.side_effect = RuntimeError("stop after create")
    with pytest.raises(RuntimeError):
        manager.run_container_once("cli-exec-y", "img", {"ZSCALER_ENABLED": "x", "A": "1"}, ["true"])
    kwargs = client.containers.create.call_args.kwargs
    assert kwargs["environment"] == {"ZSCALER_ENABLED": "x", "A": "1"}
    assert kwargs["extra_hosts"] == {"host.docker.internal": "host-gateway"}


def test_run_container_once_enabled_adds_proxy() -> None:
    """有効なとき、単発コンテナにもプロキシの環境変数が付くこと。"""
    manager, client = _manager(ZscalerSettings(enabled=True, proxy_url="http://p:1", no_proxy="n"))
    client.containers.create.side_effect = RuntimeError("stop after create")
    with pytest.raises(RuntimeError):
        manager.run_container_once("cli-exec-z", "img", {}, ["true"])
    env = client.containers.create.call_args.kwargs["environment"]
    assert env["HTTP_PROXY"] == "http://p:1"
    assert env["NO_PROXY"] == "n"
