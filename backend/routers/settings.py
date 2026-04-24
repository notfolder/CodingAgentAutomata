"""
システム設定ルーターモジュール。

以下のエンドポイントを提供する（全て admin 専用）:
- GET /api/settings システム設定取得
- PUT /api/settings システム設定更新
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.schemas.settings import SystemSettingsResponse, SystemSettingsUpdate
from backend.services.auth_service import require_admin
from backend.services.system_settings_service import SystemSettingsService
from shared.database.database import get_db
from shared.models.db import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["システム設定"])


@router.get("", response_model=SystemSettingsResponse)
def get_settings(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> SystemSettingsResponse:
    """
    システム設定を取得する（admin専用）。

    Args:
        _: admin 認証済みユーザー（権限チェック用）
        db: SQLAlchemy データベースセッション

    Returns:
        SystemSettingsResponse: システム設定レスポンス
    """
    service = SystemSettingsService(db)
    return service.get_settings()


@router.put("", response_model=SystemSettingsResponse)
def update_settings(
    data: SystemSettingsUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> SystemSettingsResponse:
    """
    システム設定を更新する（admin専用）。

    省略されたフィールドは更新しない。

    Args:
        data: システム設定更新スキーマ
        _: admin 認証済みユーザー（権限チェック用）
        db: SQLAlchemy データベースセッション

    Returns:
        SystemSettingsResponse: 更新後のシステム設定レスポンス
    """
    service = SystemSettingsService(db)
    return service.update_settings(data)
