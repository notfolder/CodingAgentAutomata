"""
システム設定関連 Pydantic スキーマ定義モジュール。

システム設定の取得・更新用スキーマを定義する。
"""

from typing import Any, Optional

from pydantic import BaseModel


class SystemSettingsResponse(BaseModel):
    """システム設定レスポンススキーマ。"""

    # F-3（Issue→MR変換）用プロンプトテンプレート
    f3_prompt_template: Optional[str] = None
    # F-4（MR処理）用プロンプトテンプレート（システムデフォルト）
    f4_prompt_template: Optional[str] = None
    # システムMCP設定（JSON文字列またはdict）
    system_mcp_config: Optional[Any] = None


class SystemSettingsUpdate(BaseModel):
    """システム設定更新スキーマ（admin専用）。"""

    # F-3プロンプトテンプレート（省略可）
    f3_prompt_template: Optional[str] = None
    # F-4プロンプトテンプレート（省略可）
    f4_prompt_template: Optional[str] = None
    # システムMCP設定（省略可）
    system_mcp_config: Optional[Any] = None
