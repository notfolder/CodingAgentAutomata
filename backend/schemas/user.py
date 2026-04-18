"""
ユーザー関連 Pydantic スキーマ定義モジュール。

ユーザーの作成・更新・レスポンス用スキーマを定義する。
Virtual Key は暗号化済みフィールドを返さず、末尾4文字のマスク値のみ返す。
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    """ユーザー作成スキーマ（admin専用）。"""

    # GitLabユーザー名（主キー）
    username: str
    # メールアドレス
    email: EmailStr
    # パスワード（平文、サービス層でハッシュ化）
    password: str
    # Virtual Key（平文、サービス層で暗号化）
    virtual_key: str
    # デフォルトCLIエージェントID
    default_cli: str
    # デフォルトLLMモデル名
    default_model: str
    # 権限ロール（admin または user）
    role: str = "user"


class UserUpdate(BaseModel):
    """ユーザー更新スキーマ（admin専用、全項目変更可能）。"""

    # メールアドレス（省略可）
    email: Optional[EmailStr] = None
    # Virtual Key（平文、省略可）
    virtual_key: Optional[str] = None
    # デフォルトCLIエージェントID（省略可）
    default_cli: Optional[str] = None
    # デフォルトLLMモデル名（省略可）
    default_model: Optional[str] = None
    # 権限ロール（省略可）
    role: Optional[str] = None
    # 有効/無効フラグ（省略可）
    is_active: Optional[bool] = None
    # システムMCP設定の適用オン/オフ（省略可）
    system_mcp_enabled: Optional[bool] = None
    # ユーザー個別MCP設定（省略可）
    user_mcp_config: Optional[Any] = None
    # ユーザー個別F-4プロンプトテンプレート（省略可）
    f4_prompt_template: Optional[str] = None


class UserUpdateSelf(BaseModel):
    """
    ユーザー自身用更新スキーマ（一般ユーザー自身のみ）。

    Virtual Key・ロール・ステータスの変更は不可。
    パスワード変更時は current_password が必須。
    """

    # メールアドレス（省略可）
    email: Optional[EmailStr] = None
    # 新しいパスワード（省略可、変更時は current_password も必要）
    password: Optional[str] = None
    # 現在のパスワード（パスワード変更時に必要）
    current_password: Optional[str] = None
    # デフォルトCLIエージェントID（省略可）
    default_cli: Optional[str] = None
    # デフォルトLLMモデル名（省略可）
    default_model: Optional[str] = None
    # システムMCP設定の適用オン/オフ（省略可）
    system_mcp_enabled: Optional[bool] = None
    # ユーザー個別MCP設定（省略可）
    user_mcp_config: Optional[Any] = None
    # ユーザー個別F-4プロンプトテンプレート（省略可）
    f4_prompt_template: Optional[str] = None


class UserResponse(BaseModel):
    """ユーザーレスポンススキーマ。virtual_key_encrypted は返さない。"""

    # GitLabユーザー名
    username: str
    # メールアドレス
    email: str
    # デフォルトCLIエージェントID
    default_cli: str
    # デフォルトLLMモデル名
    default_model: str
    # 権限ロール
    role: str
    # 有効/無効フラグ
    is_active: bool
    # システムMCP設定の適用オン/オフ
    system_mcp_enabled: bool
    # ユーザー個別MCP設定
    user_mcp_config: Optional[Any] = None
    # ユーザー個別F-4プロンプトテンプレート
    f4_prompt_template: Optional[str] = None
    # Virtual Key マスク値（末尾4文字のみ）
    virtual_key_masked: Optional[str] = None
    # 登録日時
    created_at: datetime
    # 最終更新日時
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    """ユーザー一覧レスポンススキーマ。"""

    # ユーザー一覧
    items: list[UserResponse]
    # 総件数
    total: int
    # 現在のページ番号
    page: int
    # 1ページあたりの件数
    per_page: int
