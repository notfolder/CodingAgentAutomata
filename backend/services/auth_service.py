"""
認証サービスモジュール。

JWT トークンの発行・検証、パスワードのハッシュ化・照合、
ログイン処理、FastAPI 依存性注入用のカレントユーザー取得を提供する。
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from shared.database.database import get_db
from shared.models.db import User

logger = logging.getLogger(__name__)

# JWT 設定定数
_JWT_ALGORITHM = "HS256"
_JWT_EXPIRE_HOURS = 24

# Bearer トークン抽出スキーム
_bearer_scheme = HTTPBearer()


def _get_jwt_secret() -> str:
    """
    JWT 署名シークレットキーを環境変数から取得する。

    Returns:
        str: JWT シークレットキー

    Raises:
        RuntimeError: 環境変数が未設定の場合
    """
    secret = os.environ.get("JWT_SECRET_KEY", "")
    if not secret:
        raise RuntimeError(
            "JWT_SECRET_KEY 環境変数が設定されていません。"
        )
    return secret


class AuthService:
    """
    JWT トークン発行・検証、bcrypt パスワード管理、ログイン処理を担当するサービス。
    """

    @staticmethod
    def create_access_token(data: dict) -> str:
        """
        JWT アクセストークンを発行する（有効期限24時間）。

        Args:
            data: トークンに埋め込むクレーム（例: {"sub": "username"}）

        Returns:
            str: HS256 署名された JWT トークン文字列
        """
        payload = data.copy()
        # 有効期限（現在時刻 + 24時間）を UTC で設定
        expire = datetime.now(timezone.utc) + timedelta(hours=_JWT_EXPIRE_HOURS)
        payload["exp"] = expire
        return jwt.encode(payload, _get_jwt_secret(), algorithm=_JWT_ALGORITHM)

    @staticmethod
    def verify_token(token: str) -> dict:
        """
        JWT トークンを検証し、クレームを返す。

        Args:
            token: 検証対象の JWT トークン文字列

        Returns:
            dict: トークンのクレーム（ペイロード）

        Raises:
            HTTPException 401: トークンが無効または期限切れの場合
        """
        try:
            payload = jwt.decode(
                token,
                _get_jwt_secret(),
                algorithms=[_JWT_ALGORITHM],
            )
            return payload
        except JWTError as exc:
            logger.warning("JWT 検証失敗: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="トークンが無効または期限切れです。",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

    @staticmethod
    def hash_password(password: str) -> str:
        """
        パスワードを bcrypt でハッシュ化する（コスト係数: 12）。

        Args:
            password: ハッシュ化する平文パスワード

        Returns:
            str: bcrypt ハッシュ文字列
        """
        # bcrypt でコスト12のハッシュを生成
        hashed = bcrypt.hashpw(
            password.encode("utf-8"),
            bcrypt.gensalt(rounds=12),
        )
        return hashed.decode("utf-8")

    @staticmethod
    def verify_password(plain: str, hashed: str) -> bool:
        """
        平文パスワードと bcrypt ハッシュを照合する。

        Args:
            plain: 照合する平文パスワード
            hashed: DB に保存されている bcrypt ハッシュ

        Returns:
            bool: パスワードが一致する場合 True
        """
        return bcrypt.checkpw(
            plain.encode("utf-8"),
            hashed.encode("utf-8"),
        )

    @staticmethod
    def login(username: str, password: str, db: Session) -> Optional[str]:
        """
        ユーザー名とパスワードで認証し、JWT トークンを返す。

        アクティブでないユーザーはログイン不可。

        Args:
            username: ログイン対象のユーザー名
            password: 平文パスワード
            db: SQLAlchemy データベースセッション

        Returns:
            str | None: 認証成功時は JWT トークン、失敗時は None
        """
        user = db.query(User).filter(User.username == username).first()
        if not user:
            return None

        # パスワード照合
        if not AuthService.verify_password(password, user.password_hash):
            return None

        # 非アクティブユーザーはログイン不可
        if not user.is_active:
            return None

        # JWT トークンを発行して返す（role を含める）
        return AuthService.create_access_token({"sub": user.username, "role": user.role})


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI 依存性注入用のカレントユーザー取得関数。

    Authorization: Bearer <token> ヘッダーからトークンを取得し、
    対応するUserオブジェクトを返す。

    Args:
        credentials: HTTPBearer で抽出した認証情報
        db: SQLAlchemy データベースセッション

    Returns:
        User: 認証済みユーザーオブジェクト

    Raises:
        HTTPException 401: トークンが無効またはユーザーが存在しない場合
        HTTPException 403: ユーザーが非アクティブな場合
    """
    # トークンを検証してクレームを取得
    payload = AuthService.verify_token(credentials.credentials)

    # sub クレームからユーザー名を取得
    username: Optional[str] = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="トークンにユーザー情報がありません。",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # DBからユーザーを取得
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ユーザーが見つかりません。",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 非アクティブユーザーはアクセス拒否
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="このアカウントは無効化されています。",
        )

    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """
    admin ロールを必須とする FastAPI 依存性注入関数。

    Args:
        current_user: get_current_user で取得した認証済みユーザー

    Returns:
        User: admin ロールのユーザーオブジェクト

    Raises:
        HTTPException 403: admin ロール以外の場合
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="この操作には管理者権限が必要です。",
        )
    return current_user
