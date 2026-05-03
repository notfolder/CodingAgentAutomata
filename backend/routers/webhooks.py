"""
Webhook 管理ルーターモジュール。

以下のエンドポイントを提供する（全ログインユーザー対象）:
- GET  /api/webhooks/groups                         最上位グループ一覧 + Webhook登録状況取得
- POST /api/webhooks/groups/{group_id}/hooks        指定グループへWebhook登録
- DELETE /api/webhooks/groups/{group_id}/hooks/{hook_id}  指定Webhook削除
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.schemas.webhook import GroupWithWebhookStatusResponse, WebhookCreatedResponse
from backend.services.auth_service import get_current_user
from backend.services.webhook_service import WebhookService
from shared.database.database import get_db
from shared.models.db import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhook管理"])


@router.get("/groups", response_model=list[GroupWithWebhookStatusResponse])
def list_groups_with_webhook_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[GroupWithWebhookStatusResponse]:
    """
    最上位グループ一覧とWebhook登録状況を取得する（全ログインユーザー）。

    Args:
        current_user: 認証済みユーザー
        db: SQLAlchemy データベースセッション

    Returns:
        list[GroupWithWebhookStatusResponse]: グループ + Webhook登録状況のリスト

    Raises:
        HTTPException 502: GitLab API 呼び出し失敗時
    """
    service = WebhookService(db)
    try:
        return service.get_groups_with_status()
    except RuntimeError as exc:
        logger.error("グループ一覧取得エラー: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.post(
    "/groups/{group_id}/hooks",
    response_model=WebhookCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_webhook(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WebhookCreatedResponse:
    """
    指定グループにWebhookを登録する（全ログインユーザー）。

    Args:
        group_id: GitLabグループID（正の整数）
        current_user: 認証済みユーザー
        db: SQLAlchemy データベースセッション

    Returns:
        WebhookCreatedResponse: 作成されたWebhook情報

    Raises:
        HTTPException 400: group_id が不正、またはwebhook_receive_url 未設定
        HTTPException 502: GitLab API 呼び出し失敗時
    """
    if group_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="group_id は正の整数である必要があります。",
        )

    service = WebhookService(db)
    try:
        return service.register_webhook(group_id=group_id, username=current_user.username)
    except ValueError as exc:
        logger.warning("Webhook登録エラー（設定不備）: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        logger.error("Webhook登録エラー（GitLab API）: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.delete(
    "/groups/{group_id}/hooks/{hook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_webhook(
    group_id: int,
    hook_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """
    指定グループのWebhookを削除する（全ログインユーザー）。

    Args:
        group_id: GitLabグループID（正の整数）
        hook_id: 削除するWebhookのID（正の整数）
        current_user: 認証済みユーザー
        db: SQLAlchemy データベースセッション

    Raises:
        HTTPException 400: group_id または hook_id が不正
        HTTPException 404: 対象Webhookが存在しない
        HTTPException 502: GitLab API 呼び出し失敗時
    """
    if group_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="group_id は正の整数である必要があります。",
        )
    if hook_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="hook_id は正の整数である必要があります。",
        )

    service = WebhookService(db)
    try:
        service.delete_webhook(
            group_id=group_id,
            hook_id=hook_id,
            username=current_user.username,
        )
    except KeyError as exc:
        logger.warning("Webhook削除エラー（Not Found）: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        logger.error("Webhook削除エラー（GitLab API）: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
