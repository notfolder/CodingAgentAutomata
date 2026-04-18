"""
認証ルーターモジュール。

POST /api/auth/login エンドポイントを提供する。
認証不要で、ユーザー名・パスワードを受け取り JWT トークンを発行する。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.schemas.auth import LoginRequest, TokenResponse
from backend.services.auth_service import AuthService
from shared.database.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["認証"])


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """
    ログインエンドポイント。

    ユーザー名とパスワードで認証し、JWT アクセストークンを発行する。
    認証失敗時は 401 を返す（セキュリティのためエラー詳細は返さない）。

    Args:
        data: ログインリクエスト（username, password）
        db: SQLAlchemy データベースセッション

    Returns:
        TokenResponse: JWT アクセストークンとトークン種別

    Raises:
        HTTPException 401: 認証失敗時
    """
    token = AuthService.login(data.username, data.password, db)
    if token is None:
        # 認証失敗（ユーザー名・パスワード不正または非アクティブ）
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ユーザー名またはパスワードが正しくありません。",
            headers={"WWW-Authenticate": "Bearer"},
        )

    logger.info("ログイン成功: username=%s", data.username)
    return TokenResponse(access_token=token)
