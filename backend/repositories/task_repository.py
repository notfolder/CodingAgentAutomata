"""
タスクリポジトリモジュール。

tasks テーブルへのデータアクセス処理を担当する。
タスク一覧のフィルタリングとページネーションを提供する。
"""

from typing import Optional

from sqlalchemy.orm import Session

from shared.models.db import Task


class TaskRepository:
    """tasks テーブルへのアクセスを担当するリポジトリクラス。"""

    def __init__(self, db: Session) -> None:
        """
        初期化。

        Args:
            db: SQLAlchemy データベースセッション
        """
        self._db = db

    def get_all(
        self,
        username: Optional[str] = None,
        status: Optional[str] = None,
        task_type: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[list[Task], int]:
        """
        タスク一覧を取得する。

        各フィルタは省略可。省略した場合は全件対象となる。

        Args:
            username: フィルタするユーザー名（省略可）
            status: フィルタするステータス（省略可）
            task_type: フィルタするタスク種別（省略可）
            skip: スキップ件数（ページネーション用）
            limit: 取得件数上限

        Returns:
            tuple[list[Task], int]: タスクリストと総件数のタプル
        """
        query = self._db.query(Task)

        # ユーザー名フィルタ
        if username:
            query = query.filter(Task.username == username)

        # ステータスフィルタ
        if status:
            query = query.filter(Task.status == status)

        # タスク種別フィルタ
        if task_type:
            query = query.filter(Task.task_type == task_type)

        # 総件数を取得
        total: int = query.count()

        # 作成日時の降順でページネーション適用
        tasks = (
            query.order_by(Task.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

        return tasks, total
