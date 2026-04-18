"""
システム設定サービスモジュール。

システム設定（プロンプトテンプレート・MCP設定）の取得・更新のビジネスロジックを担当する。
設定値は system_settings テーブルに key-value 形式で保存される。
"""

import json
import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.repositories.system_settings_repository import SystemSettingsRepository
from backend.schemas.settings import SystemSettingsResponse, SystemSettingsUpdate

logger = logging.getLogger(__name__)

# system_settings テーブルで使用するキー定数
_KEY_F3_PROMPT = "f3_prompt_template"
_KEY_F4_PROMPT = "f4_prompt_template"
_KEY_SYSTEM_MCP = "system_mcp_config"


def _parse_json_or_str(value: Optional[str]) -> Any:
    """
    文字列を JSON としてパースする。パースできない場合は文字列のまま返す。

    Args:
        value: パース対象の文字列（None の場合はそのまま返す）

    Returns:
        Any: パースされた値、またはそのままの文字列
    """
    if value is None:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        # JSON でない場合はそのままの文字列として返す
        return value


def _serialize_value(value: Any) -> Optional[str]:
    """
    設定値を文字列にシリアライズする。

    dict/list は JSON 文字列化し、str はそのまま返す。

    Args:
        value: シリアライズ対象の値

    Returns:
        Optional[str]: シリアライズされた文字列、または None
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    # dict/list の場合は JSON 文字列化
    return json.dumps(value, ensure_ascii=False)


class SystemSettingsService:
    """システム設定の取得・更新を担当するサービスクラス。"""

    def __init__(self, db: Session) -> None:
        """
        初期化。

        Args:
            db: SQLAlchemy データベースセッション
        """
        self._db = db
        self._repo = SystemSettingsRepository(db)

    def get_settings(self) -> SystemSettingsResponse:
        """
        システム設定を全件取得してレスポンスを構築する。

        Returns:
            SystemSettingsResponse: システム設定レスポンス
        """
        # 各設定値をキーで取得
        f3_setting = self._repo.get(_KEY_F3_PROMPT)
        f4_setting = self._repo.get(_KEY_F4_PROMPT)
        mcp_setting = self._repo.get(_KEY_SYSTEM_MCP)

        return SystemSettingsResponse(
            f3_prompt_template=f3_setting.value if f3_setting else None,
            f4_prompt_template=f4_setting.value if f4_setting else None,
            # system_mcp_config は JSON 文字列の場合に dict に変換して返す
            system_mcp_config=_parse_json_or_str(
                mcp_setting.value if mcp_setting else None
            ),
        )

    def update_settings(self, data: SystemSettingsUpdate) -> SystemSettingsResponse:
        """
        システム設定を更新する（admin専用）。

        省略されたフィールドは更新しない。

        Args:
            data: システム設定更新スキーマ

        Returns:
            SystemSettingsResponse: 更新後のシステム設定レスポンス
        """
        # 更新するキーと値の辞書を構築（None は除外）
        updates: dict[str, str] = {}

        if data.f3_prompt_template is not None:
            updates[_KEY_F3_PROMPT] = data.f3_prompt_template

        if data.f4_prompt_template is not None:
            updates[_KEY_F4_PROMPT] = data.f4_prompt_template

        if data.system_mcp_config is not None:
            # dict/list の場合は JSON 文字列に変換して保存
            serialized = _serialize_value(data.system_mcp_config)
            if serialized is not None:
                updates[_KEY_SYSTEM_MCP] = serialized

        # 一括 upsert
        if updates:
            self._repo.upsert_many(updates)

        return self.get_settings()
