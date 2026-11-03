"""CLIAdapterResolver の opencode のモデル名の判定と設定の組み立ての単体テスト。"""

import json

import pytest

from consumer.cli_adapter_resolver import CLIAdapterResolver
from shared.models.db import CLIAdapter

_URL = "http://litellm:4000"
_KEY = "sk-virtual-key"
_ANTHROPIC_OPTIONS = {"baseURL": f"{_URL}/v1", "apiKey": _KEY}


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
        start_command_template="claude -p --model {model} --mcp-config '{mcp_config}'",
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
        ("claude-opus-5-5", ("anthropic", "claude-opus-5-5")),
        ("claude-haiku-4-5-20251001", ("anthropic", "claude-haiku-4-5-20251001")),
        ("gpt-5.5", ("openai", "gpt-5.5")),
        ("anthropic/claude-opus-5-5", ("anthropic", "claude-opus-5-5")),
        ("openai/gpt-4o-mini", ("openai", "gpt-4o-mini")),
        ("", ("openai", "gpt-4o-mini")),
        ("litellm/org/model", ("litellm", "org/model")),
    ],
)
def test_split_opencode_model(model: str, expected: tuple[str, str]) -> None:
    """/ があれば最初の / で分け、無ければ claude- で始まるかでプロバイダを決める。"""
    assert CLIAdapterResolver.split_opencode_model(model) == expected


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("claude-opus-5-5", "anthropic/claude-opus-5-5"),
        ("gpt-5.5", "openai/gpt-5.5"),
        ("anthropic/claude-opus-5-5", "anthropic/claude-opus-5-5"),
        ("openai/gpt-4o-mini", "openai/gpt-4o-mini"),
        ("", "openai/gpt-4o-mini"),
    ],
)
def test_qualify_opencode_model(model: str, expected: str) -> None:
    """opencode に渡す名前は常に「プロバイダ/モデル」の形になる。"""
    assert CLIAdapterResolver.qualify_opencode_model(model) == expected


@pytest.mark.parametrize(
    ("model", "expected"),
    [("claude-opus-5-5", "anthropic/claude-opus-5-5"), ("gpt-5.5", "openai/gpt-5.5"), ("openai/gpt-4o-mini", "openai/gpt-4o-mini")],
)
def test_start_command_opencode_uses_qualified_model(model: str, expected: str) -> None:
    """opencode の起動コマンドの --model には、プロバイダを付けた名前が入る。"""
    command = _resolver().build_start_command(_opencode_adapter(), {"model": model})
    assert command == f"cat /tmp/prompt.txt | opencode run - --model {expected}"


def test_start_command_claude_keeps_model() -> None:
    """Claude Code の起動コマンドには、書いた名前がそのまま入る。"""
    command = _resolver().build_start_command(_claude_adapter(), {"model": "claude-opus-5-5"})
    assert command == "claude -p --model claude-opus-5-5"


@pytest.mark.parametrize("model", ["claude-opus-5-5", "anthropic/claude-opus-5-5"])
def test_anthropic_config_has_v1_api_key_and_small_model(model: str) -> None:
    """Claude のモデルでは、/ の有無にかかわらず /v1 付きの baseURL、apiKey、つないだ small_model が入る。"""
    config = CLIAdapterResolver.build_opencode_provider_config(model, _URL, _KEY)
    assert config == {
        "provider": {"anthropic": {"options": _ANTHROPIC_OPTIONS}},
        "small_model": "anthropic/claude-opus-5-5",
    }


@pytest.mark.parametrize("url", [f"{_URL}/", f"{_URL}/v1", f"{_URL}/v1/"])
def test_anthropic_base_url_v1_not_duplicated(url: str) -> None:
    """URL の末尾に / や /v1 があっても /v1 が二重にならない。"""
    config = CLIAdapterResolver.build_opencode_provider_config("claude-opus-5-5", url, _KEY)
    assert config["provider"]["anthropic"]["options"]["baseURL"] == f"{_URL}/v1"


def test_anthropic_without_key_omits_api_key() -> None:
    """Virtual Key が無ければ apiKey を入れない。"""
    config = CLIAdapterResolver.build_opencode_provider_config("claude-opus-5-5", _URL, None)
    assert "apiKey" not in config["provider"]["anthropic"]["options"]


@pytest.mark.parametrize(
    "model,small_model",
    [("openai/gpt-4o-mini", "openai/gpt-4o-mini"), ("gpt-5.5", "openai/gpt-5.5"), ("", "openai/gpt-4o-mini")],
)
def test_openai_config_has_base_url_and_small_model(model: str, small_model: str) -> None:
    """OpenAI のモデルでは、baseURL は URL のまま入り、small_model に本体のモデルが入る。"""
    config = CLIAdapterResolver.build_opencode_provider_config(model, _URL, _KEY)
    assert config == {"provider": {"openai": {"options": {"baseURL": _URL}}}, "small_model": small_model}


def test_other_provider_config_has_small_model() -> None:
    """openai・anthropic 以外のプロバイダでも、small_model に「プロバイダ/モデル」の名前が入る。"""
    config = CLIAdapterResolver.build_opencode_provider_config("litellm/org/model", _URL, _KEY)
    assert config == {"provider": {"litellm": {"options": {"baseURL": _URL}}}, "small_model": "litellm/org/model"}


def test_build_env_vars_opencode_unprefixed_claude() -> None:
    """opencode のアダプタ（env_mappings は OPENAI_API_KEY のまま）で、プロバイダ名の無い Claude の名前でも JSON と OPENAI_API_KEY が入る。"""
    mcp = json.dumps({"mcpServers": {"gitlab": {"command": "x"}}})
    env = _resolver().build_env_vars(
        _opencode_adapter(),
        {"llm_api_key": _KEY, "llm_base_url": _URL, "model": "claude-haiku-4-5-20251001", "mcp_config": mcp},
    )
    assert env["OPENAI_API_KEY"] == _KEY
    content = json.loads(env["OPENCODE_CONFIG_CONTENT"])
    assert content["provider"] == {"anthropic": {"options": _ANTHROPIC_OPTIONS}}
    assert content["small_model"] == "anthropic/claude-haiku-4-5-20251001"
    assert content["mcp"] == {"gitlab": {"command": "x"}}


def test_build_env_vars_opencode_openai() -> None:
    """opencode のアダプタで OpenAI のモデルなら、JSON に baseURL と本体のモデルの small_model が入る。"""
    env = _resolver().build_env_vars(
        _opencode_adapter(),
        {"llm_api_key": _KEY, "llm_base_url": _URL, "model": "gpt-5.5"},
    )
    assert env["OPENAI_API_KEY"] == _KEY
    assert json.loads(env["OPENCODE_CONFIG_CONTENT"]) == {
        "provider": {"openai": {"options": {"baseURL": _URL}}},
        "small_model": "openai/gpt-5.5",
    }


def test_build_env_vars_claude_unchanged() -> None:
    """Claude Code のアダプタ（設定の JSON を渡す環境変数が無い）では、出力が変わらない。"""
    env = _resolver().build_env_vars(
        _claude_adapter(),
        {"llm_api_key": _KEY, "llm_base_url": _URL, "model": "claude-opus-5-5"},
    )
    assert env == {"ANTHROPIC_API_KEY": _KEY, "ANTHROPIC_BASE_URL": _URL}
