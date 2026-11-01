"""ZscalerSettings の単体テスト。"""

from consumer.zscaler_settings import ZscalerSettings


def test_from_env_enabled_reads_proxy_and_no_proxy() -> None:
    """有効なとき、プロキシの宛先と除外宛先を読むこと。"""
    settings = ZscalerSettings.from_env(
        {
            "ZSCALER_ENABLED": "true",
            "HTTPS_PROXY": "http://proxy.corp:8080",
            "NO_PROXY": "localhost,backend",
        }
    )
    assert settings.enabled is True
    assert settings.proxy_url == "http://proxy.corp:8080"
    assert settings.no_proxy == "localhost,backend"


def test_from_env_disabled_or_missing() -> None:
    """false・値なし・不正な値は無効として扱うこと。"""
    for env in ({"ZSCALER_ENABLED": "false", "HTTPS_PROXY": "http://p:1"}, {}, {"ZSCALER_ENABLED": "yes"}):
        settings = ZscalerSettings.from_env(env)
        assert settings.enabled is False
        assert settings.proxy_url == ""


def test_build_cli_env_enabled() -> None:
    """有効なとき、大文字版と小文字版のプロキシの環境変数を返すこと。"""
    env = ZscalerSettings(enabled=True, proxy_url="http://p:8080", no_proxy="localhost").build_cli_env()
    assert env == {
        "ZSCALER_ENABLED": "true",
        "HTTP_PROXY": "http://p:8080",
        "HTTPS_PROXY": "http://p:8080",
        "http_proxy": "http://p:8080",
        "https_proxy": "http://p:8080",
        "NO_PROXY": "localhost",
        "no_proxy": "localhost",
    }


def test_build_cli_env_disabled() -> None:
    """無効なとき、ZSCALER_ENABLED=false だけを返すこと。"""
    assert ZscalerSettings(enabled=False).build_cli_env() == {"ZSCALER_ENABLED": "false"}


def test_build_instruction() -> None:
    """有効なときだけ指示文を返し、指示文に必須の内容が含まれること。"""
    instruction = ZscalerSettings(enabled=True, proxy_url="http://p:1").build_instruction()
    assert "Zscaler" in instruction
    assert "/usr/local/share/ca-certificates/zscaler.crt" in instruction
    assert "/etc/ssl/certs/ca-certificates.crt" in instruction
    assert "NO_PROXY" in instruction
    assert "コミットしない" in instruction
    assert "Firefox" in instruction
    assert ZscalerSettings(enabled=False).build_instruction() == ""
