"""
タスクサービスモジュール。

タスク一覧取得のビジネスロジックを担当する。
admin は全タスクを取得可能、一般ユーザーは自分のタスクのみ取得可能。
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from backend.repositories.task_repository import TaskRepository
from backend.schemas.task import TaskListResponse, TaskResponse
from shared.models.db import User

logger = logging.getLogger(__name__)

# 1ページあたりの表示件数
_PAGE_SIZE = 20


class TaskService:
    """タスク一覧取得処理を担当するサービスクラス。"""

    def __init__(self, db: Session) -> None:
        """
        初期化。

        Args:
            db: SQLAlchemy データベースセッション
        """
        self._db = db
        self._repo = TaskRepository(db)

    def list_tasks(
        self,
        current_user: User,
        username: Optional[str] = None,
        status: Optional[str] = None,
        task_type: Optional[str] = None,
        page: int = 1,
    ) -> TaskListResponse:
        """
        タスク一覧を取得する。

        admin は全タスクを取得可能。
        一般ユーザーは自分のタスクのみ取得可能（username フィルタを自動適用）。

        Args:
            current_user: 認証済みカレントユーザー
            username: フィルタするユーザー名（省略可）
            status: フィルタするステータス（省略可）
            task_type: フィルタするタスク種別（省略可）
            page: ページ番号（1始まり）

        Returns:
            TaskListResponse: タスク一覧レスポンス
        """
        # 一般ユーザーは自分のタスクのみに絞り込む
        if current_user.role != "admin":
            username = current_user.username

        skip = (page - 1) * _PAGE_SIZE
        tasks, total = self._repo.get_all(
            username=username,
            status=status,
            task_type=task_type,
            skip=skip,
            limit=_PAGE_SIZE,
        )

        items = [TaskResponse.model_validate(t) for t in tasks]

        return TaskListResponse(
            items=items,
            total=total,
            page=page,
            per_page=_PAGE_SIZE,
        )
