"""
GitLab ポーリングループモジュール。

POLLING_INTERVAL_SECONDS 秒ごとに GitLab API を問い合わせ、
設定されたプロジェクトの Issue/MR を取得して GitLabEventHandler に渡す。
"""

import asyncio
import logging

from shared.config.config import Settings, get_project_ids

# ロガーを設定
logger = logging.getLogger(__name__)


class PollingLoop:
    """
    POLLING_INTERVAL_SECONDS 秒ごとに GitLab API を問い合わせるポーリングループ。

    GITLAB_PROJECT_IDS 環境変数（カンマ区切り）に設定されたプロジェクトIDを対象に
    Issue 一覧と MR 一覧を取得し、GitLabEventHandler に処理を委譲する。
    asyncio で非同期に動作し、WebhookServer と並行して実行される。
    """

    def __init__(
        self,
        gitlab_client: object,
        event_handler: object,
        settings: Settings,
    ) -> None:
        """
        PollingLoop を初期化する。

        Args:
            gitlab_client: GitLabClient インスタンス
            event_handler: GitLabEventHandler インスタンス
            settings: アプリケーション設定インスタンス
        """
        self._gitlab_client = gitlab_client
        self._event_handler = event_handler
        self._settings = settings
        logger.debug(
            "PollingLoop initialized: interval=%ds",
            settings.polling_interval_seconds,
        )

    async def start(self) -> None:
        """
        ポーリングループを開始する。

        GITLAB_PROJECT_IDS に設定された全プロジェクトを対象に
        POLLING_INTERVAL_SECONDS 秒ごとにポーリングを実行する。
        プロジェクトIDが設定されていない場合はポーリングをスキップして待機する。

        このメソッドは asyncio.gather で WebhookServer と並行実行されることを想定しており、
        明示的にキャンセルされるまで実行を継続する。
        """
        interval: int = self._settings.polling_interval_seconds
        project_ids: list[int] = get_project_ids(self._settings)

        if not project_ids:
            logger.warning(
                "PollingLoop: GITLAB_PROJECT_IDS is not set. Polling is disabled."
            )
            # プロジェクトIDが未設定でもループは継続して待機する
            while True:
                await asyncio.sleep(interval)

        logger.info(
            "PollingLoop started: project_ids=%s, interval=%ds",
            project_ids,
            interval,
        )

        while True:
            # 全プロジェクトをポーリングする
            for project_id in project_ids:
                await self._poll_project(project_id)

            # 次のポーリングまで待機する
            logger.debug("PollingLoop: sleeping %ds until next poll", interval)
            await asyncio.sleep(interval)

    async def _poll_project(self, project_id: int) -> None:
        """
        指定プロジェクトの Issue/MR をポーリングして処理する。

        GitLab API 呼び出しはブロッキング操作のため、
        asyncio のイベントループをブロックしないよう run_in_executor を使用する。

        Args:
            project_id: ポーリング対象の GitLab プロジェクトID
        """
        logger.debug("PollingLoop: polling project_id=%d", project_id)

        loop = asyncio.get_running_loop()

        # Issue 一覧の取得（ブロッキング操作を executor で実行）
        try:
            issues: list[dict] = await loop.run_in_executor(
                None,
                lambda: self._gitlab_client.list_issues(
                    project_id,
                    state="opened",
                ),
            )
        except Exception as exc:
            logger.error(
                "PollingLoop: failed to list issues for project_id=%d: %s",
                project_id,
                exc,
                exc_info=True,
            )
            issues = []

        # MR 一覧の取得（ブロッキング操作を executor で実行）
        try:
            mrs: list[dict] = await loop.run_in_executor(
                None,
                lambda: self._gitlab_client.list_merge_requests(
                    project_id,
                    state="opened",
                ),
            )
        except Exception as exc:
            logger.error(
                "PollingLoop: failed to list MRs for project_id=%d: %s",
                project_id,
                exc,
                exc_info=True,
            )
            mrs = []

        logger.debug(
            "PollingLoop: project_id=%d fetched %d issues, %d MRs",
            project_id,
            len(issues),
            len(mrs),
        )

        # イベントハンドラーに処理を委譲する
        try:
            self._event_handler.handle_polling_items(issues, mrs, project_id)
        except Exception as exc:
            logger.error(
                "PollingLoop: handle_polling_items error for project_id=%d: %s",
                project_id,
                exc,
                exc_info=True,
            )
