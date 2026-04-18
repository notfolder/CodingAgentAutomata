"""
タスクメッセージ Pydantic モデルモジュール。

Producer から RabbitMQ に投入するタスクメッセージ、
および Consumer がデキューして処理するタスクメッセージの型定義を提供する。
"""

from pydantic import BaseModel


class TaskMessage(BaseModel):
    """
    タスクメッセージモデル。

    Producer が RabbitMQ に投入し、Consumer がデキューして処理するメッセージの構造。
    task_type に応じて IssueToMRConverter または MRProcessor が処理を担当する。
    """

    # タスクの一意識別子（UUID v4 文字列）
    task_uuid: str

    # タスク種別（"issue" または "merge_request"）
    task_type: str

    # GitLabプロジェクトID
    gitlab_project_id: int

    # Issue IIDまたはMR IID
    source_iid: int

    # 実行対象ユーザー名（GitLabユーザー名）
    username: str
