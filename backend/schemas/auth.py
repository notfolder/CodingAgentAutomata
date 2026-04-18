"""
認証関連 Pydantic スキーマ定義モジュール。

ログインリクエストとJWTトークンレスポンスを定義する。
"""

from pydantic import BaseModel


class LoginRequest(BaseModel):
    """ログインリクエストスキーマ。"""

    # GitLabユーザー名
    username: str
    # パスワード
    password: str


class TokenResponse(BaseModel):
    """JWTトークンレスポンススキーマ。"""

    # JWTアクセストークン
    access_token: str
    # トークン種別（常に "bearer"）
    token_type: str = "bearer"
