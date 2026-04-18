"""
Producer エントリーポイントモジュール。

WebhookServer と PollingLoop を asyncio.gather で並行起動する。
起動順:
    1. アプリケーション設定・各クライアントを初期化する
    2. GitLabEventHandler・DuplicateCheckService を初期化する
    3. WebhookServer と PollingLoop を asyncio.gather で並行起動する
"""

import asyncio
import logging
import sys

from shared.config.config import get_settings
from shared.database.database import SessionLocal
from shared.gitlab_client.gitlab_client import GitLabClient
from shared.messaging.rabbitmq_client import RabbitMQClient

from producer.gitlab_event_handler import GitLabEventHandler
from producer.polling_loop import PollingLoop
from producer.webhook_server import WebhookServer

# ロガー設定（basicConfig はプロセス起動時に一度だけ設定する）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# RabbitMQ タスクキュー名
_TASK_QUEUE_NAME = "tasks"


async def main() -> None:
    """
    Producer のメインエントリーポイント。

    1. アプリケーション設定・GitLabClient・RabbitMQClient・DB セッションファクトリを初期化する
    2. GitLabEventHandler を初期化する
    3. WebhookServer と PollingLoop を asyncio.gather で並行起動する
    """
    logger.info("Producer starting...")

    # ------------------------------------------------------------------
    # 1. アプリケーション設定の読み込み
    # ------------------------------------------------------------------
    settings = get_settings()

    # 必須設定の確認（未設定の場合は警告ログを出力して続行）
    if not settings.gitlab_pat:
        logger.warning("GITLAB_PAT is not set. GitLab API calls will fail.")
    if not settings.gitlab_bot_name:
        logger.warning("GITLAB_BOT_NAME is not set. No tasks will be triggered.")
    if not settings.gitlab_webhook_secret:
        logger.warning(
            "GITLAB_WEBHOOK_SECRET is not set. Webhook requests will not be verified."
        )

    # ------------------------------------------------------------------
    # 2. 各クライアントの初期化
    # ------------------------------------------------------------------

    # GitLab クライアントの初期化
    gitlab_client = GitLabClient(
        pat=settings.gitlab_pat,
        api_url=settings.gitlab_api_url,
    )

    # RabbitMQ クライアントの初期化と接続
    rabbitmq_client = RabbitMQClient(
        rabbitmq_url=settings.rabbitmq_url,
        queue_name=_TASK_QUEUE_NAME,
    )
    try:
        rabbitmq_client.connect()
    except Exception as exc:
        logger.error("Producer: RabbitMQ connection failed: %s", exc, exc_info=True)
        raise

    # DB セッションファクトリ（contextmanager として使用するためラムダでラップ）
    # SessionLocal は contextmanager をサポートするため直接使用する
    from contextlib import contextmanager

    @contextmanager
    def db_session_factory():
        """SQLAlchemy セッションのコンテキストマネージャーファクトリ。"""
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    # ------------------------------------------------------------------
    # 3. イベントハンドラーの初期化
    # ------------------------------------------------------------------
    event_handler = GitLabEventHandler(
        gitlab_client=gitlab_client,
        rabbitmq_client=rabbitmq_client,
        db_session_factory=db_session_factory,
        settings=settings,
    )

    # ------------------------------------------------------------------
    # 4. WebhookServer と PollingLoop の並行起動
    # ------------------------------------------------------------------
    webhook_server = WebhookServer(
        event_handler=event_handler,
        settings=settings,
    )
    polling_loop = PollingLoop(
        gitlab_client=gitlab_client,
        event_handler=event_handler,
        settings=settings,
    )

    logger.info("Producer: starting WebhookServer and PollingLoop concurrently...")

    try:
        # asyncio.gather で WebhookServer と PollingLoop を並行起動する
        await asyncio.gather(
            webhook_server.start(),
            polling_loop.start(),
        )
    except asyncio.CancelledError:
        logger.info("Producer: received cancellation, shutting down...")
    except Exception as exc:
        logger.error("Producer: unexpected error: %s", exc, exc_info=True)
        raise
    finally:
        # クリーンアップ: RabbitMQ 接続をクローズする
        rabbitmq_client.close()
        logger.info("Producer stopped.")


if __name__ == "__main__":
    asyncio.run(main())
