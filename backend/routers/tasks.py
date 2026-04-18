"""
タスク管理ルーターモジュール。

以下のエンドポイントを提供する:
- GET /api/tasks (admin: 全タスク / user: 自分のみ、フィルタ対応・ページネーション)
"""

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.schemas.task import TaskListResponse
from backend.services.auth_service import get_current_user
from backend.services.task_service import TaskService
from shared.database.database import get_db
from shared.models.db import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["タスク管理"])


@router.get("", response_model=TaskListResponse)
def list_tasks(
    username: str = Query(default=None, description="ユーザー名フィルタ（admin専用）"),
    status: str = Query(default=None, description="ステータスフィルタ"),
    task_type: str = Query(default=None, description="タスク種別フィルタ"),
    page: int = Query(default=1, ge=1, description="ページ番号"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TaskListResponse:
    """
    タスク一覧を取得する。

    admin は全タスクを取得可能（username フィルタも使用可能）。
    一般ユーザーは自分のタスクのみ取得可能（username フィルタは無視される）。

    Args:
        username: フィルタするユーザー名（admin専用、省略可）
        status: フィルタするステータス（省略可）
        task_type: フィルタするタスク種別（省略可）
        page: ページ番号（1始まり）
        current_user: 認証済みカレントユーザー
        db: SQLAlchemy データベースセッション

    Returns:
        TaskListResponse: タスク一覧レスポンス
    """
    service = TaskService(db)
    return service.list_tasks(
        current_user=current_user,
        username=username,
        status=status,
        task_type=task_type,
        page=page,
    )
