"""
タスク関連 Pydantic スキーマ定義モジュール。

タスク履歴のレスポンス用スキーマを定義する。
cli_log は容量が大きすぎるため含めない。
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class TaskResponse(BaseModel):
    """タスクレスポンススキーマ。cli_log は含めない。"""

    # タスク一意識別子
    task_uuid: str
    # タスク種別（issue または merge_request）
    task_type: str
    # GitLabプロジェクトID
    gitlab_project_id: int
    # Issue IIDまたはMR IID
    source_iid: int
    # 実行対象ユーザー名
    username: str
    # ステータス（pending/running/completed/failed）
    status: str
    # 使用したCLIエージェントID
    cli_type: Optional[str] = None
    # 使用したモデル名
    model: Optional[str] = None
    # エラー内容（失敗時のみ）
    error_message: Optional[str] = None
    # タスク作成日時
    created_at: datetime
    # 処理開始日時
    started_at: Optional[datetime] = None
    # 処理完了日時
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TaskListResponse(BaseModel):
    """タスク一覧レスポンススキーマ。"""

    # タスク一覧
    items: list[TaskResponse]
    # 総件数
    total: int
    # 現在のページ番号
    page: int
    # 1ページあたりの件数
    per_page: int
