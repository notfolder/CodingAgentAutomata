"""
ユーザー管理ルーターモジュール。

以下のエンドポイントを提供する:
- GET  /api/users           (admin) ユーザー一覧取得（前方一致検索・ページネーション）
- POST /api/users           (admin) ユーザー作成
- GET  /api/users/{username} (admin: 全員 / user: 自分のみ)
- PUT  /api/users/{username} (admin: 全項目 / user: 制限項目のみ)
- DELETE /api/users/{username} (admin)
- GET  /api/users/{username}/model-candidates  モデル候補一覧取得
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
from backend.services.model_candidate_service import ModelCandidateService
from backend.services.user_service import UserService
from backend.services.virtual_key_service import VirtualKeyService
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


@router.get("/{username}/model-candidates", response_model=list[str])
async def get_model_candidates(
    username: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[str]:
    """
    対象ユーザーの Virtual Key を使用して利用可能なモデル候補一覧を取得する。

    対象ユーザーの virtual_key_encrypted を復号し、
    ModelCandidateService 経由で LiteLLM から候補を取得する。
    取得に失敗した場合は空リストを返す。

    Args:
        username: モデル候補を取得する対象のユーザー名
        current_user: 認証済みカレントユーザー
        db: SQLAlchemy データベースセッション

    Returns:
        list[str]: モデル ID の文字列リスト。取得失敗時は空リスト
    """
    # 権限チェック: admin または自分自身のみアクセス可能
    if current_user.role != "admin" and current_user.username != username:
        logger.warning(
            "get_model_candidates: 権限なし current_user=%s, target=%s",
            current_user.username,
            username,
        )
        return []

    # ユーザーの Virtual Key を取得・復号する
    service = UserService(db)
    try:
        user_response = service.get_user(username, current_user)
    except Exception as exc:
        logger.warning(
            "get_model_candidates: ユーザー取得失敗 username=%s: %s",
            username,
            exc,
        )
        return []

    # Virtual Key を復号して取得する
    try:
        from backend.repositories.user_repository import UserRepository
        repo = UserRepository(db)
        user = repo.get_by_username(username)
        if user is None or not user.virtual_key_encrypted:
            return []
        vk_service = VirtualKeyService()
        plain_key = vk_service.decrypt(user.virtual_key_encrypted)
    except Exception as exc:
        logger.warning(
            "get_model_candidates: Virtual Key 復号失敗 username=%s: %s",
            username,
            exc,
        )
        return []

    # ModelCandidateService でモデル候補を取得する（失敗時は空リスト）
    try:
        candidate_service = ModelCandidateService()
        models = await candidate_service.fetch_models(plain_key)
        return models
    except Exception as exc:
        logger.warning(
            "get_model_candidates: モデル候補取得失敗 username=%s: %s",
            username,
            exc,
        )
        return []
