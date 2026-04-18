"""
ユーザー管理ルーターモジュール。

以下のエンドポイントを提供する:
- GET  /api/users           (admin) ユーザー一覧取得（前方一致検索・ページネーション）
- POST /api/users           (admin) ユーザー作成
- GET  /api/users/{username} (admin: 全員 / user: 自分のみ)
- PUT  /api/users/{username} (admin: 全項目 / user: 制限項目のみ)
- DELETE /api/users/{username} (admin)
"""

import logging

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from backend.schemas.user import (
    UserCreate,
    UserListResponse,
    UserResponse,
    UserUpdate,
    UserUpdateSelf,
)
from backend.services.auth_service import get_current_user, require_admin
from backend.services.user_service import UserService
from shared.database.database import get_db
from shared.models.db import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["ユーザー管理"])


@router.get("", response_model=UserListResponse)
def list_users(
    search: str = Query(default=None, description="usernameの前方一致検索"),
    page: int = Query(default=1, ge=1, description="ページ番号"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserListResponse:
    """
    ユーザー一覧を取得する（admin専用）。

    Args:
        search: username の前方一致検索文字列（省略可）
        page: ページ番号（1始まり）
        _: admin 認証済みユーザー（権限チェック用）
        db: SQLAlchemy データベースセッション

    Returns:
        UserListResponse: ユーザー一覧レスポンス
    """
    service = UserService(db)
    return service.list_users(search=search, page=page)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    data: UserCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserResponse:
    """
    ユーザーを新規作成する（admin専用）。

    Args:
        data: ユーザー作成スキーマ
        _: admin 認証済みユーザー（権限チェック用）
        db: SQLAlchemy データベースセッション

    Returns:
        UserResponse: 作成されたユーザー情報
    """
    service = UserService(db)
    return service.create_user(data)


@router.get("/{username}", response_model=UserResponse)
def get_user(
    username: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserResponse:
    """
    ユーザー情報を取得する。

    admin は全ユーザーを取得可能。一般ユーザーは自分のみ取得可能。

    Args:
        username: 取得対象のユーザー名
        current_user: 認証済みカレントユーザー
        db: SQLAlchemy データベースセッション

    Returns:
        UserResponse: ユーザー情報
    """
    service = UserService(db)
    return service.get_user(username, current_user)


@router.put("/{username}", response_model=UserResponse)
def update_user(
    username: str,
    data: UserUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserResponse:
    """
    ユーザー情報を管理者権限で更新する（admin専用、全項目変更可能）。

    Args:
        username: 更新対象のユーザー名
        data: ユーザー更新スキーマ（admin用）
        current_user: admin 認証済みユーザー
        db: SQLAlchemy データベースセッション

    Returns:
        UserResponse: 更新後のユーザー情報
    """
    service = UserService(db)
    return service.update_user_admin(username, data)


@router.put("/{username}/me", response_model=UserResponse)
def update_user_self(
    username: str,
    data: UserUpdateSelf,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserResponse:
    """
    一般ユーザーが自分自身の情報を更新する（制限項目のみ変更可能）。

    Virtual Key・ロール・ステータスの変更は不可。

    Args:
        username: 更新対象のユーザー名（自分自身のみ）
        data: ユーザー自身用更新スキーマ
        current_user: 認証済みカレントユーザー
        db: SQLAlchemy データベースセッション

    Returns:
        UserResponse: 更新後のユーザー情報
    """
    service = UserService(db)
    return service.update_user_self(username, data, current_user)


@router.delete("/{username}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    username: str,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    """
    ユーザーを削除する（admin専用）。

    Args:
        username: 削除対象のユーザー名
        _: admin 認証済みユーザー（権限チェック用）
        db: SQLAlchemy データベースセッション
    """
    service = UserService(db)
    service.delete_user(username)
