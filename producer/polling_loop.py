"""
GitLab ポーリングループモジュール。

POLLING_INTERVAL_SECONDS 秒ごとに GitLab API を問い合わせ、
設定されたプロジェクトの Issue/MR を取得して GitLabEventHandler に渡す。
"""

import asyncio
import logging
from collections import defaultdict

from shared.config.config import Settings

# ロガーを設定
logger = logging.getLogger(__name__)


class PollingLoop:
    """
    POLLING_INTERVAL_SECONDS 秒ごとに GitLab API を問い合わせるポーリングループ。

    全プロジェクト横断で bot アサイン済みの open な Issue/MR を取得し、
    GitLabEventHandler に処理を委譲する。
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

        全プロジェクト横断で bot アサイン済みの open Issue/MR を対象に
        POLLING_INTERVAL_SECONDS 秒ごとにポーリングを実行する。

        このメソッドは asyncio.gather で WebhookServer と並行実行されることを想定しており、
        明示的にキャンセルされるまで実行を継続する。
        """
        interval: int = self._settings.polling_interval_seconds
        bot_name: str = self._settings.gitlab_bot_name
        bot_label: str = self._settings.gitlab_bot_label

        if not bot_name:
            logger.warning("PollingLoop: GITLAB_BOT_NAME is not set. Polling is disabled.")
            while True:
                await asyncio.sleep(interval)

        logger.info(
            "PollingLoop started: target=all bot-assigned issues/mrs, bot=%s, interval=%ds",
            bot_name,
            interval,
        )

        while True:
            await self._poll_all_projects(bot_name, bot_label)

            # 次のポーリングまで待機する
            logger.debug("PollingLoop: sleeping %ds until next poll", interval)
            await asyncio.sleep(interval)

    async def _poll_all_projects(self, bot_name: str, bot_label: str) -> None:
        """
        全プロジェクト横断で bot アサイン済みの Issue/MR をポーリングして処理する。

        GitLab API 呼び出しはブロッキング操作のため、
        asyncio のイベントループをブロックしないよう run_in_executor を使用する。
        """
        logger.debug("PollingLoop: polling all projects for bot-assigned items")

        loop = asyncio.get_running_loop()

        # 全プロジェクト横断 Issue 一覧の取得（ブロッキング操作を executor で実行）
        try:
            issues: list[dict] = await loop.run_in_executor(
                None,
                lambda: self._gitlab_client.list_assigned_issues_all_projects(
                    assignee_username=bot_name,
                    labels=[bot_label] if bot_label else None,
                    state="opened",
                ),
            )
        except Exception as exc:
            logger.error(
                "PollingLoop: failed to list assigned issues across all projects: %s",
                exc,
                exc_info=True,
            )
            issues = []

        # 全プロジェクト横断 MR 一覧の取得（ブロッキング操作を executor で実行）
        try:
            mrs: list[dict] = await loop.run_in_executor(
                None,
                lambda: self._gitlab_client.list_assigned_merge_requests_all_projects(
                    assignee_username=bot_name,
                    labels=[bot_label] if bot_label else None,
                    state="opened",
                ),
            )
        except Exception as exc:
            logger.error(
                "PollingLoop: failed to list assigned MRs across all projects: %s",
                exc,
                exc_info=True,
            )
            mrs = []

        logger.debug(
            "PollingLoop: fetched %d issues, %d MRs across all projects",
            len(issues),
            len(mrs),
        )

        issues_by_project: dict[int, list[dict]] = defaultdict(list)
        for issue in issues:
            issue_project_id = issue.get("project_id")
            if issue_project_id:
                issues_by_project[int(issue_project_id)].append(issue)

        mrs_by_project: dict[int, list[dict]] = defaultdict(list)
        for mr in mrs:
            # Global MR API は target_project_id または project_id が入る
            mr_project_id = mr.get("target_project_id") or mr.get("project_id")
            if mr_project_id:
                mrs_by_project[int(mr_project_id)].append(mr)

        project_ids = sorted(set(issues_by_project.keys()) | set(mrs_by_project.keys()))

        # プロジェクト単位にイベントハンドラーへ処理委譲する
        for project_id in project_ids:
            try:
                self._event_handler.handle_polling_items(
                    issues_by_project.get(project_id, []),
                    mrs_by_project.get(project_id, []),
                    project_id,
                )
            except Exception as exc:
                logger.error(
                    "PollingLoop: handle_polling_items error for project_id=%d: %s",
                    project_id,
                    exc,
                    exc_info=True,
                )
