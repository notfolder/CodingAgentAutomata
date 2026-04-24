"""
CLIアダプタ関連 Pydantic スキーマ定義モジュール。

CLIアダプタの作成・更新・レスポンス用スキーマを定義する。
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class CLIAdapterCreate(BaseModel):
    """CLIアダプタ作成スキーマ（admin専用）。"""

    # CLIエージェント識別子（例: claude, opencode）
    cli_id: str
    # cli-execコンテナイメージ名・タグ
    container_image: str
    # 起動コマンドテンプレート
    start_command_template: str
    # 情報名→環境変数名マッピング
    env_mappings: dict[str, Any]
    # 設定内容をJSON環境変数で渡す場合の環境変数名（省略可）
    config_content_env: Optional[str] = None
    # 組み込みアダプタフラグ（デフォルト: False）
    is_builtin: bool = False


class CLIAdapterUpdate(BaseModel):
    """CLIアダプタ更新スキーマ（admin専用）。"""

    # cli-execコンテナイメージ名・タグ（省略可）
    container_image: Optional[str] = None
    # 起動コマンドテンプレート（省略可）
    start_command_template: Optional[str] = None
    # 情報名→環境変数名マッピング（省略可）
    env_mappings: Optional[dict[str, Any]] = None
    # 設定内容をJSON環境変数で渡す場合の環境変数名（省略可）
    config_content_env: Optional[str] = None


class CLIAdapterResponse(BaseModel):
    """CLIアダプタレスポンススキーマ。"""

    # CLIエージェント識別子
    cli_id: str
    # cli-execコンテナイメージ名・タグ
    container_image: str
    # 起動コマンドテンプレート
    start_command_template: str
    # 情報名→環境変数名マッピング
    env_mappings: dict[str, Any]
    # 設定内容をJSON環境変数で渡す場合の環境変数名
    config_content_env: Optional[str] = None
    # 組み込みアダプタフラグ
    is_builtin: bool
    # 登録日時
    created_at: datetime
    # 最終更新日時
    updated_at: datetime

    model_config = {"from_attributes": True}
