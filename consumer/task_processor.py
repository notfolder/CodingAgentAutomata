"""
タスク種別に応じた F-3/F-4 処理のディスパッチャーモジュール。

RabbitMQ からデキューしたタスクメッセージを解析し、
task_type に応じて IssueToMRConverter または MRProcessor に処理を委譲する。
"""

import asyncio
import logging
from typing import Callable

from sqlalchemy.orm import Session

from shared.models.task import TaskMessage

# ロガーを設定
logger = logging.getLogger(__name__)


class TaskProcessor:
    """
    タスク種別（issue/merge_request）に応じて
    IssueToMRConverter または MRProcessor を実行するディスパッチャークラス。
    """

    def __init__(
        self,
        issue_converter,
        mr_processor,
        cli_log_masker,
        db_session_factory: Callable[[], Session],
    ) -> None:
        """
        初期化。

        Args:
            issue_converter: IssueToMRConverter インスタンス
            mr_processor: MRProcessor インスタンス
            cli_log_masker: CLILogMasker インスタンス
            db_session_factory: SQLAlchemy Session ファクトリ関数
        """
        self._issue_converter = issue_converter
        self._mr_processor = mr_processor
        self._cli_log_masker = cli_log_masker
        self._db_session_factory: Callable[[], Session] = db_session_factory

    async def process(self, task_message: dict) -> None:
        """
        タスクメッセージを受信して F-3 または F-4 処理を実行する。

        task_type が "issue" の場合は IssueToMRConverter、
        task_type が "merge_request" の場合は MRProcessor に処理を委譲する。

        Args:
            task_message: RabbitMQ からデキューしたタスクメッセージ辞書
                - task_uuid: タスク UUID
                - task_type: タスク種別（"issue" または "merge_request"）
                - gitlab_project_id: GitLab プロジェクト ID
                - source_iid: Issue/MR の IID
                - username: 処理対象の GitLab ユーザー名
        """
        try:
            # タスクメッセージを Pydantic モデルでバリデーション
            msg: TaskMessage = TaskMessage(**task_message)
        except Exception as exc:
            logger.error("TaskProcessor: タスクメッセージのパースに失敗しました: %s", exc)
            return

        logger.info(
            "TaskProcessor: タスク処理開始 task_uuid=%s, task_type=%s",
            msg.task_uuid,
            msg.task_type,
        )

        if msg.task_type == "issue":
            # F-3: Issue→MR 変換処理（同期処理を非同期コンテキストで実行）
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._issue_converter.convert,
                msg.task_uuid,
                msg.gitlab_project_id,
                msg.source_iid,
                msg.username,
            )

        elif msg.task_type == "merge_request":
            # F-4: MR 処理（非同期処理）
            await self._mr_processor.process(
                task_uuid=msg.task_uuid,
                project_id=msg.gitlab_project_id,
                mr_iid=msg.source_iid,
                username=msg.username,
            )

        else:
            logger.warning(
                "TaskProcessor: 未知の task_type='%s' task_uuid=%s",
                msg.task_type,
                msg.task_uuid,
            )
