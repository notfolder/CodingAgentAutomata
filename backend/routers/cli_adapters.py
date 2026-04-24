"""
CLIアダプタ管理ルーターモジュール。

以下のエンドポイントを提供する（全て admin 専用）:
- GET    /api/cli-adapters          CLIアダプタ一覧取得
- POST   /api/cli-adapters          CLIアダプタ作成
- PUT    /api/cli-adapters/{cli_id} CLIアダプタ更新
- DELETE /api/cli-adapters/{cli_id} CLIアダプタ削除
"""

import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.schemas.cli_adapter import (
    CLIAdapterCreate,
    CLIAdapterResponse,
    CLIAdapterUpdate,
)
from backend.services.auth_service import require_admin
from backend.services.cli_adapter_service import CLIAdapterService
from shared.database.database import get_db
from shared.models.db import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cli-adapters", tags=["CLIアダプタ管理"])


@router.get("", response_model=list[CLIAdapterResponse])
def list_adapters(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[CLIAdapterResponse]:
    """
    全CLIアダプタ一覧を取得する（admin専用）。

    Args:
        _: admin 認証済みユーザー（権限チェック用）
        db: SQLAlchemy データベースセッション

    Returns:
        list[CLIAdapterResponse]: CLIアダプタ一覧
    """
    service = CLIAdapterService(db)
    return service.list_adapters()


@router.post(
    "",
    response_model=CLIAdapterResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_adapter(
    data: CLIAdapterCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CLIAdapterResponse:
    """
    CLIアダプタを新規作成する（admin専用）。

    Args:
        data: CLIアダプタ作成スキーマ
        _: admin 認証済みユーザー（権限チェック用）
        db: SQLAlchemy データベースセッション

    Returns:
        CLIAdapterResponse: 作成されたCLIアダプタ情報
    """
    service = CLIAdapterService(db)
    return service.create_adapter(data)


@router.put("/{cli_id}", response_model=CLIAdapterResponse)
def update_adapter(
    cli_id: str,
    data: CLIAdapterUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CLIAdapterResponse:
    """
    CLIアダプタ情報を更新する（admin専用）。

    Args:
        cli_id: 更新対象のCLIアダプタID
        data: CLIアダプタ更新スキーマ
        _: admin 認証済みユーザー（権限チェック用）
        db: SQLAlchemy データベースセッション

    Returns:
        CLIAdapterResponse: 更新後のCLIアダプタ情報
    """
    service = CLIAdapterService(db)
    return service.update_adapter(cli_id, data)


@router.delete("/{cli_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_adapter(
    cli_id: str,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    """
    CLIアダプタを削除する（admin専用）。

    is_builtin=True のアダプタ、またはユーザーが参照中のアダプタは削除不可。

    Args:
        cli_id: 削除対象のCLIアダプタID
        _: admin 認証済みユーザー（権限チェック用）
        db: SQLAlchemy データベースセッション
    """
    service = CLIAdapterService(db)
    service.delete_adapter(cli_id)
