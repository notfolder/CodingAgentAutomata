"""CLIAdapterResolver の opencode のプロバイダの判定と設定の組み立ての単体テスト。"""

import json

import pytest

from consumer.cli_adapter_resolver import CLIAdapterResolver
from shared.models.db import CLIAdapter

_URL = "http://litellm:4000"
_KEY = "sk-virtual-key"


def _opencode_adapter() -> CLIAdapter:
    """組み込みの opencode のアダプタと同じ設定のオブジェクトを作る。"""
    return CLIAdapter(
        cli_id="opencode",
        container_image="coding-agent-cli-exec-opencode:latest",
        start_command_template="cat /tmp/prompt.txt | opencode run - --model {model}",
        env_mappings={"llm_api_key": "OPENAI_API_KEY"},
        config_content_env="OPENCODE_CONFIG_CONTENT",
        is_builtin=True,
    )


def _claude_adapter() -> CLIAdapter:
    """組み込みの Claude Code のアダプタと同じ設定のオブジェクトを作る。"""
    return CLIAdapter(
        cli_id="claude",
        container_image="coding-agent-cli-exec-claude:latest",
        start_command_template="claude -p --model {model}",
        env_mappings={"llm_api_key": "ANTHROPIC_API_KEY", "llm_base_url": "ANTHROPIC_BASE_URL"},
        config_content_env=None,
        is_builtin=True,
    )


def _resolver() -> CLIAdapterResolver:
    """DB を使わない CLIAdapterResolver を作る。"""
    return CLIAdapterResolver(db_session_factory=lambda: None)


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("anthropic/claude-opus-5-5", ("anthropic", "claude-opus-5-5")),
        ("openai/gpt-4o-mini", ("openai", "gpt-4o-mini")),
        ("gpt-4o-mini", ("openai", "gpt-4o-mini")),
        ("", ("openai", "gpt-4o-mini")),
        ("litellm/org/model", ("litellm", "org/model")),
    ],
)
def test_split_opencode_model(model: str, expected: tuple[str, str]) -> None:
    """モデル名を最初の / でプロバイダとモデルに分け、/ が無ければ openai とみなす。"""
    assert CLIAdapterResolver.split_opencode_model(model) == expected


def test_anthropic_config_has_v1_api_key_and_small_model() -> None:
    """anthropic のモデルでは /v1 付きの baseURL、apiKey、small_model が入る。"""
    config = CLIAdapterResolver.build_opencode_provider_config("anthropic/claude-opus-5-5", _URL, _KEY)
    assert config == {
        "provider": {"anthropic": {"options": {"baseURL": f"{_URL}/v1", "apiKey": _KEY}}},
        "small_model": "anthropic/claude-opus-5-5",
    }


@pytest.mark.parametrize("url", [f"{_URL}/", f"{_URL}/v1", f"{_URL}/v1/"])
def test_anthropic_base_url_v1_not_duplicated(url: str) -> None:
    """URL の末尾に / や /v1 があっても /v1 が二重にならない。"""
    config = CLIAdapterResolver.build_opencode_provider_config("anthropic/claude-opus-5-5", url, _KEY)
    assert config["provider"]["anthropic"]["options"]["baseURL"] == f"{_URL}/v1"


def test_anthropic_without_key_omits_api_key() -> None:
    """Virtual Key が無ければ apiKey を入れない。"""
    config = CLIAdapterResolver.build_opencode_provider_config("anthropic/claude-opus-5-5", _URL, None)
    assert "apiKey" not in config["provider"]["anthropic"]["options"]


@pytest.mark.parametrize(("model", "provider"), [("openai/gpt-4o-mini", "openai"), ("gpt-4o-mini", "openai"), ("", "openai")])
def test_openai_config_is_unchanged(model: str, provider: str) -> None:
    """openai と / の無い名前、空の名前では、従来どおり baseURL だけが入る。"""
    config = CLIAdapterResolver.build_opencode_provider_config(model, _URL, _KEY)
    assert config == {"provider": {provider: {"options": {"baseURL": _URL}}}}


def test_build_env_vars_opencode_anthropic() -> None:
    """opencode のアダプタ（env_mappings は OPENAI_API_KEY のまま）で、JSON と OPENAI_API_KEY の両方が入る。"""
    mcp = json.dumps({"mcpServers": {"gitlab": {"command": "x"}}})
    env = _resolver().build_env_vars(
        _opencode_adapter(),
        {"llm_api_key": _KEY, "llm_base_url": _URL, "model": "anthropic/claude-haiku-4-5-20251001", "mcp_config": mcp},
    )
    assert env["OPENAI_API_KEY"] == _KEY
    content = json.loads(env["OPENCODE_CONFIG_CONTENT"])
    assert content["provider"] == {"anthropic": {"options": {"baseURL": f"{_URL}/v1", "apiKey": _KEY}}}
    assert content["small_model"] == "anthropic/claude-haiku-4-5-20251001"
    assert content["mcp"] == {"gitlab": {"command": "x"}}


def test_build_env_vars_opencode_openai_unchanged() -> None:
    """opencode のアダプタで openai のモデルなら、JSON は従来と同じになる。"""
    env = _resolver().build_env_vars(
        _opencode_adapter(),
        {"llm_api_key": _KEY, "llm_base_url": _URL, "model": "openai/gpt-4o-mini"},
    )
    assert env["OPENAI_API_KEY"] == _KEY
    assert json.loads(env["OPENCODE_CONFIG_CONTENT"]) == {"provider": {"openai": {"options": {"baseURL": _URL}}}}


def test_build_env_vars_claude_unchanged() -> None:
    """Claude Code のアダプタ（設定の JSON を渡す環境変数が無い）では、出力が変わらない。"""
    env = _resolver().build_env_vars(
        _claude_adapter(),
        {"llm_api_key": _KEY, "llm_base_url": _URL, "model": "claude-opus-5-5"},
    )
    assert env == {"ANTHROPIC_API_KEY": _KEY, "ANTHROPIC_BASE_URL": _URL}
