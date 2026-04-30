"""
ユーザーサービスモジュール。

ユーザーの一覧取得・作成・更新（admin/自分）・削除のビジネスロジックを担当する。
Virtual Key の暗号化/復号、パスワードハッシュ化もここで行う。
"""

import asyncio
import concurrent.futures
import logging
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.repositories.user_repository import UserRepository
from backend.schemas.user import (
    UserCreate,
    UserListResponse,
    UserResponse,
    UserUpdate,
    UserUpdateSelf,
)
from backend.services.auth_service import AuthService
from backend.services.model_candidate_service import ModelCandidateService
from backend.services.virtual_key_service import VirtualKeyService
from shared.models.db import User

logger = logging.getLogger(__name__)

# 1ページあたりの表示件数
_PAGE_SIZE = 20


def _build_user_response(user: User, vk_service: VirtualKeyService) -> UserResponse:
    """
    User ORM オブジェクトから UserResponse を構築する。

    virtual_key_encrypted を復号し、末尾4文字のマスク値を生成する。

    Args:
        user: User ORM オブジェクト
        vk_service: VirtualKeyService インスタンス

    Returns:
        UserResponse: レスポンス用スキーマオブジェクト
    """
    virtual_key_masked: Optional[str] = None
    try:
        # Virtual Key を復号して末尾4文字のマスク値を生成
        plain_key = vk_service.decrypt(user.virtual_key_encrypted)
        if len(plain_key) >= 4:
            virtual_key_masked = "****" + plain_key[-4:]
        else:
            virtual_key_masked = "****"
    except Exception as exc:
        logger.warning(
            "Virtual Key のマスク生成に失敗しました (username=%s): %s",
            user.username,
            exc,
        )

    return UserResponse(
        username=user.username,
        email=user.email,
        default_cli=user.default_cli,
        default_model=user.default_model,
        role=user.role,
        is_active=user.is_active,
        system_mcp_enabled=user.system_mcp_enabled,
        user_mcp_config=user.user_mcp_config,
        f4_prompt_template=user.f4_prompt_template,
        virtual_key_masked=virtual_key_masked,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


class UserService:
    """ユーザーのCRUD処理を担当するサービスクラス。"""

    def __init__(self, db: Session) -> None:
        """
        初期化。

        Args:
            db: SQLAlchemy データベースセッション
        """
        self._db = db
        self._repo = UserRepository(db)
        self._vk_service = VirtualKeyService()

    def _validate_virtual_key(self, key: str) -> None:
        """
        Virtual Key を LiteLLM エンドポイントで検証する。

        検証に失敗した場合は HTTPException(400) を送出する。
        LiteLLM エンドポイントへの接続自体に失敗した場合も 400 を送出する。

        Args:
            key: 検証対象の Virtual Key

        Raises:
            HTTPException 400: キー検証失敗時
        """
        service = ModelCandidateService()

        def _run() -> tuple[bool, str]:
            """別スレッドで非同期検証を実行する。"""
            return asyncio.run(service.validate_key(key))

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run)
            try:
                is_valid, error_reason = future.result(timeout=15.0)
            except concurrent.futures.TimeoutError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="LLMキーの検証に失敗しました: 接続タイムアウト",
                )

        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"LLMキーの検証に失敗しました: {error_reason}",
            )

    def list_users(
        self,
        search: Optional[str] = None,
        page: int = 1,
    ) -> UserListResponse:
        """
        ユーザー一覧を取得する（admin専用）。

        Args:
            search: username の前方一致検索文字列（省略可）
            page: ページ番号（1始まり）

        Returns:
            UserListResponse: ユーザー一覧レスポンス
        """
        skip = (page - 1) * _PAGE_SIZE
        users, total = self._repo.get_all(search=search, skip=skip, limit=_PAGE_SIZE)

        items = [_build_user_response(u, self._vk_service) for u in users]

        return UserListResponse(
            items=items,
            total=total,
            page=page,
            per_page=_PAGE_SIZE,
        )

    def get_user(self, username: str, current_user: User) -> UserResponse:
        """
        ユーザー情報を取得する。

        admin は全ユーザーを取得可能。一般ユーザーは自分のみ取得可能。

        Args:
            username: 取得対象のユーザー名
            current_user: 認証済みカレントユーザー

        Returns:
            UserResponse: ユーザーレスポンス

        Raises:
            HTTPException 403: 一般ユーザーが他者を取得しようとした場合
            HTTPException 404: ユーザーが存在しない場合
        """
        # 権限チェック: 一般ユーザーは自分のみ
        if current_user.role != "admin" and current_user.username != username:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="他のユーザー情報を参照する権限がありません。",
            )

        user = self._repo.get_by_username(username)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"ユーザー '{username}' が見つかりません。",
            )

        return _build_user_response(user, self._vk_service)

    def create_user(self, data: UserCreate) -> UserResponse:
        """
        ユーザーを新規作成する（admin専用）。

        Args:
            data: ユーザー作成スキーマ

        Returns:
            UserResponse: 作成されたユーザーのレスポンス

        Raises:
            HTTPException 409: メールアドレスまたはユーザー名が既に存在する場合
            HTTPException 400: ロールが不正な場合
        """
        # ユーザー名重複チェック
        if self._repo.get_by_username(data.username):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"ユーザー名 '{data.username}' は既に使用されています。",
            )

        # メールアドレス重複チェック
        if self._repo.email_exists(data.email):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"メールアドレス '{data.email}' は既に使用されています。",
            )

        # ロール検証
        if data.role not in ("admin", "user"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ロールは 'admin' または 'user' を指定してください。",
            )

        # パスワードをハッシュ化
        password_hash = AuthService.hash_password(data.password)

        # Virtual Key を暗号化
        virtual_key_encrypted = self._vk_service.encrypt(data.virtual_key)

        # User ORM オブジェクトを作成
        new_user = User(
            username=data.username,
            email=data.email,
            password_hash=password_hash,
            virtual_key_encrypted=virtual_key_encrypted,
            default_cli=data.default_cli,
            default_model=data.default_model,
            role=data.role,
        )

        created = self._repo.create(new_user)
        return _build_user_response(created, self._vk_service)

    def update_user_admin(self, username: str, data: UserUpdate) -> UserResponse:
        """
        ユーザー情報を管理者権限で更新する（admin専用、全項目変更可能）。

        Args:
            username: 更新対象のユーザー名
            data: ユーザー更新スキーマ（admin用）

        Returns:
            UserResponse: 更新後のユーザーレスポンス

        Raises:
            HTTPException 404: ユーザーが存在しない場合
            HTTPException 409: メールアドレスが重複する場合
            HTTPException 400: ロールが不正な場合
        """
        user = self._repo.get_by_username(username)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"ユーザー '{username}' が見つかりません。",
            )

        # 各フィールドを更新（指定されたもののみ）
        if data.email is not None:
            # メールアドレス重複チェック（自分自身は除外）
            if self._repo.email_exists(data.email, exclude_username=username):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"メールアドレス '{data.email}' は既に使用されています。",
                )
            user.email = data.email

        if data.virtual_key is not None:
            # Virtual Key を保存前に LiteLLM エンドポイントで検証する
            self._validate_virtual_key(data.virtual_key)
            # Virtual Key を再暗号化
            user.virtual_key_encrypted = self._vk_service.encrypt(data.virtual_key)

        if data.default_cli is not None:
            user.default_cli = data.default_cli

        if data.default_model is not None:
            user.default_model = data.default_model

        if data.role is not None:
            if data.role not in ("admin", "user"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="ロールは 'admin' または 'user' を指定してください。",
                )
            user.role = data.role

        if data.is_active is not None:
            user.is_active = data.is_active

        if data.system_mcp_enabled is not None:
            user.system_mcp_enabled = data.system_mcp_enabled

        if data.user_mcp_config is not None:
            user.user_mcp_config = data.user_mcp_config

        if data.f4_prompt_template is not None:
            user.f4_prompt_template = data.f4_prompt_template

        updated = self._repo.update(user)
        return _build_user_response(updated, self._vk_service)

    def update_user_self(
        self,
        username: str,
        data: UserUpdateSelf,
        current_user: User,
    ) -> UserResponse:
        """
        一般ユーザーが自分自身の情報を更新する。

        Virtual Key・ロール・ステータスの変更は不可。
        パスワード変更時は current_password が必要。

        Args:
            username: 更新対象のユーザー名（自分自身のみ）
            data: ユーザー自身用更新スキーマ
            current_user: 認証済みカレントユーザー

        Returns:
            UserResponse: 更新後のユーザーレスポンス

        Raises:
            HTTPException 403: 他のユーザーを更新しようとした場合
            HTTPException 404: ユーザーが存在しない場合
            HTTPException 400: current_password が不正な場合
            HTTPException 409: メールアドレスが重複する場合
        """
        # 自分自身のみ更新可能
        if current_user.username != username:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="他のユーザー情報を変更する権限がありません。",
            )

        user = self._repo.get_by_username(username)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"ユーザー '{username}' が見つかりません。",
            )

        # メールアドレス更新
        if data.email is not None:
            if self._repo.email_exists(data.email, exclude_username=username):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"メールアドレス '{data.email}' は既に使用されています。",
                )
            user.email = data.email

        # パスワード変更（current_password が必要）
        if data.password is not None:
            if not data.current_password:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="パスワード変更には current_password が必要です。",
                )
            if not AuthService.verify_password(
                data.current_password, user.password_hash
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="現在のパスワードが正しくありません。",
                )
            user.password_hash = AuthService.hash_password(data.password)

        if data.default_cli is not None:
            user.default_cli = data.default_cli

        if data.default_model is not None:
            user.default_model = data.default_model

        if data.system_mcp_enabled is not None:
            user.system_mcp_enabled = data.system_mcp_enabled

        if data.user_mcp_config is not None:
            user.user_mcp_config = data.user_mcp_config

        if data.f4_prompt_template is not None:
            user.f4_prompt_template = data.f4_prompt_template

        updated = self._repo.update(user)
        return _build_user_response(updated, self._vk_service)

    def delete_user(self, username: str) -> None:
        """
        ユーザーを削除する（admin専用）。

        Args:
            username: 削除対象のユーザー名

        Raises:
            HTTPException 404: ユーザーが存在しない場合
        """
        deleted = self._repo.delete(username)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"ユーザー '{username}' が見つかりません。",
            )
