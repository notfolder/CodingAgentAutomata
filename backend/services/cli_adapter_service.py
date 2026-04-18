"""
CLIアダプタサービスモジュール。

CLIアダプタの一覧取得・作成・更新・削除のビジネスロジックを担当する。
is_builtin=True のアダプタの削除は拒否する。
ユーザーに参照されているアダプタの削除も拒否する。
"""

import logging
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.repositories.cli_adapter_repository import CLIAdapterRepository
from backend.schemas.cli_adapter import (
    CLIAdapterCreate,
    CLIAdapterResponse,
    CLIAdapterUpdate,
)
from shared.models.db import CLIAdapter

logger = logging.getLogger(__name__)


class CLIAdapterService:
    """CLIアダプタの CRUD 処理を担当するサービスクラス。"""

    def __init__(self, db: Session) -> None:
        """
        初期化。

        Args:
            db: SQLAlchemy データベースセッション
        """
        self._db = db
        self._repo = CLIAdapterRepository(db)

    def list_adapters(self) -> list[CLIAdapterResponse]:
        """
        全CLIアダプタ一覧を取得する。

        Returns:
            list[CLIAdapterResponse]: CLIアダプタ一覧レスポンス
        """
        adapters = self._repo.get_all()
        return [CLIAdapterResponse.model_validate(a) for a in adapters]

    def create_adapter(self, data: CLIAdapterCreate) -> CLIAdapterResponse:
        """
        CLIアダプタを新規作成する（admin専用）。

        Args:
            data: CLIアダプタ作成スキーマ

        Returns:
            CLIAdapterResponse: 作成されたCLIアダプタのレスポンス

        Raises:
            HTTPException 409: cli_id が既に存在する場合
        """
        # cli_id 重複チェック
        if self._repo.get_by_id(data.cli_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"CLIアダプタID '{data.cli_id}' は既に使用されています。",
            )

        new_adapter = CLIAdapter(
            cli_id=data.cli_id,
            container_image=data.container_image,
            start_command_template=data.start_command_template,
            env_mappings=data.env_mappings,
            config_content_env=data.config_content_env,
            is_builtin=data.is_builtin,
        )

        created = self._repo.create(new_adapter)
        return CLIAdapterResponse.model_validate(created)

    def update_adapter(
        self,
        cli_id: str,
        data: CLIAdapterUpdate,
    ) -> CLIAdapterResponse:
        """
        CLIアダプタ情報を更新する（admin専用）。

        Args:
            cli_id: 更新対象のCLIアダプタID
            data: CLIアダプタ更新スキーマ

        Returns:
            CLIAdapterResponse: 更新後のCLIアダプタレスポンス

        Raises:
            HTTPException 404: CLIアダプタが存在しない場合
        """
        adapter = self._repo.get_by_id(cli_id)
        if not adapter:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"CLIアダプタ '{cli_id}' が見つかりません。",
            )

        # 指定されたフィールドのみ更新
        if data.container_image is not None:
            adapter.container_image = data.container_image

        if data.start_command_template is not None:
            adapter.start_command_template = data.start_command_template

        if data.env_mappings is not None:
            adapter.env_mappings = data.env_mappings

        if data.config_content_env is not None:
            adapter.config_content_env = data.config_content_env

        updated = self._repo.update(adapter)
        return CLIAdapterResponse.model_validate(updated)

    def delete_adapter(self, cli_id: str) -> None:
        """
        CLIアダプタを削除する（admin専用）。

        is_builtin=True のアダプタ、またはユーザーが参照中のアダプタは削除不可。

        Args:
            cli_id: 削除対象のCLIアダプタID

        Raises:
            HTTPException 404: CLIアダプタが存在しない場合
            HTTPException 400: is_builtin=True のアダプタを削除しようとした場合
            HTTPException 400: ユーザーがデフォルトCLIとして参照中の場合
        """
        adapter = self._repo.get_by_id(cli_id)
        if not adapter:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"CLIアダプタ '{cli_id}' が見つかりません。",
            )

        # 組み込みアダプタは削除不可
        if adapter.is_builtin:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"組み込みアダプタ '{cli_id}' は削除できません。",
            )

        # ユーザーに参照されているアダプタは削除不可
        if self._repo.is_referenced_by_users(cli_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"CLIアダプタ '{cli_id}' はユーザーのデフォルトCLIとして"
                    "使用中のため削除できません。"
                ),
            )

        self._repo.delete(cli_id)
