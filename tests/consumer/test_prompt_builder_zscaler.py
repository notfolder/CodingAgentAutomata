"""PromptBuilder の Zscaler の指示文の付加の単体テスト。"""

from typing import Optional

import pytest

from consumer.prompt_builder import PromptBuilder
from consumer.zscaler_settings import ZscalerSettings

_F3 = "F3 {issue_title}"
_F4 = "F4 {mr_description} {mr_comments} {branch_name} {repository_url}"


class _FakePromptBuilder(PromptBuilder):
    """DB の代わりに決まったテンプレートを返す PromptBuilder。"""

    def _get_system_setting(self, key: str) -> Optional[str]:
        """テンプレートを返す。"""
        return {"f3_prompt_template": _F3, "f4_prompt_template": _F4}.get(key)


def _builder(enabled: bool) -> PromptBuilder:
    """Zscaler 設定を指定して PromptBuilder を作る。"""
    settings = ZscalerSettings(enabled=enabled, proxy_url="http://p:8080" if enabled else "")
    return _FakePromptBuilder(db_session_factory=lambda: None, zscaler_settings=settings)


def _f3(builder: PromptBuilder) -> str:
    """F-3 のプロンプトを作る。"""
    return builder.build_f3_prompt("題名", "説明", "コメント", "proj", "http://repo", "- main")


def _f4(builder: PromptBuilder, user_template: Optional[str] = None) -> str:
    """F-4 のプロンプトを作る。"""
    return builder.build_f4_prompt("指示", "コメント", "feature/x", "http://repo", user_f4_template=user_template)


@pytest.mark.parametrize(
    "make",
    [
        _f3,
        _f4,
        lambda b: _f4(b, "ユーザー個別 {mr_description}"),
    ],
)
def test_instruction_appended_when_enabled(make) -> None:
    """有効なとき、F-3・F-4（システム設定とユーザー個別）の末尾に指示文が付くこと。"""
    prompt = make(_builder(True))
    instruction = ZscalerSettings(enabled=True).build_instruction()
    assert prompt.endswith(instruction)
    assert "\n\n---\n\n" + instruction in prompt


@pytest.mark.parametrize("make", [_f3, _f4])
def test_instruction_not_appended_when_disabled(make) -> None:
    """無効なとき、指示文が付かないこと。"""
    prompt = make(_builder(False))
    assert "Zscaler" not in prompt


def test_default_is_disabled() -> None:
    """Zscaler 設定を渡さなければ無効として扱うこと。"""
    builder = _FakePromptBuilder(db_session_factory=lambda: None)
    assert "Zscaler" not in _f3(builder)
