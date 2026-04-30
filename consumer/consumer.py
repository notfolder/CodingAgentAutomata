"""
Consumer エントリーポイント・ConsumerWorker モジュール。

RabbitMQ からタスクをデキューして TaskProcessor にディスパッチするワーカーを起動する。
SIGTERM / SIGINT 受信時はグレースフルシャットダウンを行い、
処理中のタスクを完了させてからプロセスを終了する。
"""

import asyncio
import logging
import signal
import sys

from shared.shutdown_state import request_shutdown, reset_shutdown

# ロガー設定（標準出力に INFO 以上を出力）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


class ConsumerWorker:
    """
    RabbitMQ からタスクをデキューして TaskProcessor にディスパッチするワーカー。

    RabbitMQClient の consume（ブロッキング）を実行し、
    メッセージ受信ごとの実処理は別スレッド経由で asyncio.run() する。
    SIGTERM 受信時は shutdown() を呼び出すことでグレースフルに停止する。
    """

    def __init__(self, rabbitmq_client, task_processor) -> None:
        """
        初期化。

        Args:
            rabbitmq_client: RabbitMQClient インスタンス
            task_processor: TaskProcessor インスタンス
        """
        self._rabbitmq_client = rabbitmq_client
        self._task_processor = task_processor

    def shutdown(self) -> None:
        """
        グレースフルシャットダウンを開始する。

        RabbitMQ の consume ループに停止シグナルを送る。
        現在処理中のタスクは完了まで待ってから停止する。
        """
        logger.info("ConsumerWorker: シャットダウン要求を受信しました。処理中タスクの完了を待ちます。")
        self._rabbitmq_client.stop_consuming()

    def start(self) -> None:
        """
        RabbitMQ の consume を開始する（ブロッキング）。

        メッセージを受信するたびに TaskProcessor.process を asyncio.run() で実行する。
        実際のタスク実行は RabbitMQ の consume スレッドとは別スレッドで行われるため、
        長時間処理中も heartbeat が維持される。
        shutdown() が呼ばれると start_consuming() が戻り、このメソッドも終了する。
        """
        logger.info("ConsumerWorker: RabbitMQ consume を開始します")

        def _callback(message: dict) -> None:
            """RabbitMQ からメッセージを受信したときのコールバック。"""
            logger.info("ConsumerWorker: メッセージを受信しました: %s", message)
            # 非同期タスク処理を同期コールバック内で実行
            asyncio.run(self._task_processor.process(message))

        self._rabbitmq_client.consume(_callback)


async def main() -> None:
    """
    Consumer の全サービスを初期化して ConsumerWorker を起動する。

    起動順序:
    1. 設定読み込み
    2. DB セッションファクトリ初期化
    3. 各サービスの初期化
    4. RabbitMQ 接続
    5. ConsumerWorker 起動
    """
    # ------------------------------------------------------------------
    # 設定読み込み
    # ------------------------------------------------------------------
    from shared.config.config import get_settings, Settings
    settings: Settings = get_settings()
    reset_shutdown()

    # ------------------------------------------------------------------
    # DB セッションファクトリ初期化
    # ------------------------------------------------------------------
    from shared.database.database import SessionLocal
    db_session_factory = SessionLocal

    # ------------------------------------------------------------------
    # GitLab クライアント初期化
    # ------------------------------------------------------------------
    from shared.gitlab_client.gitlab_client import GitLabClient
    gitlab_client = GitLabClient(
        pat=settings.gitlab_pat,
        api_url=settings.gitlab_api_url,
    )

    # ------------------------------------------------------------------
    # RabbitMQ クライアント初期化
    # ------------------------------------------------------------------
    from shared.messaging.rabbitmq_client import RabbitMQClient
    rabbitmq_client = RabbitMQClient(
        rabbitmq_url=settings.rabbitmq_url,
        queue_name="tasks",
    )
    rabbitmq_client.connect()

    # ------------------------------------------------------------------
    # 各サービスの初期化
    # ------------------------------------------------------------------
    from consumer.virtual_key_service import VirtualKeyService
    from consumer.cli_log_masker import CLILogMasker
    from consumer.cli_adapter_resolver import CLIAdapterResolver
    from consumer.prompt_builder import PromptBuilder
    from consumer.cli_container_manager import CLIContainerManager
    from consumer.progress_manager import ProgressManager
    from consumer.issue_to_mr_converter import IssueToMRConverter
    from consumer.mr_processor import MRProcessor
    from consumer.task_processor import TaskProcessor

    virtual_key_service = VirtualKeyService()
    cli_log_masker = CLILogMasker()
    cli_adapter_resolver = CLIAdapterResolver(db_session_factory=db_session_factory)
    prompt_builder = PromptBuilder(db_session_factory=db_session_factory)
    # DB から全アダプターのコンテナイメージを取得し、ウォームアップに使用する
    # （CLIContainerManager 初期化より先に cli_adapter_resolver を生成しておく必要がある）
    warmup_images = cli_adapter_resolver.fetch_all_container_images()
    cli_container_manager = CLIContainerManager(warmup_images=warmup_images)

    # ProgressManager ファクトリ関数
    # project_id と mr_iid を受け取って ProgressManager インスタンスを返す
    def progress_manager_factory(project_id: int, mr_iid: int) -> ProgressManager:
        return ProgressManager(
            gitlab_client=gitlab_client,
            project_id=project_id,
            mr_iid=mr_iid,
            interval_sec=settings.progress_report_interval_sec,
            summary_lines=settings.progress_report_summary_lines,
            buffer_max_lines=settings.progress_report_buffer_max_lines,
        )

    # IssueToMRConverter（F-3）
    issue_converter = IssueToMRConverter(
        gitlab_client=gitlab_client,
        cli_container_manager=cli_container_manager,
        cli_adapter_resolver=cli_adapter_resolver,
        prompt_builder=prompt_builder,
        virtual_key_service=virtual_key_service,
        settings=settings,
        db_session_factory=db_session_factory,
    )

    # MRProcessor（F-4）
    mr_processor = MRProcessor(
        gitlab_client=gitlab_client,
        cli_container_manager=cli_container_manager,
        cli_adapter_resolver=cli_adapter_resolver,
        progress_manager_factory=progress_manager_factory,
        prompt_builder=prompt_builder,
        virtual_key_service=virtual_key_service,
        settings=settings,
        db_session_factory=db_session_factory,
    )

    # TaskProcessor（ディスパッチャー）
    task_processor = TaskProcessor(
        issue_converter=issue_converter,
        mr_processor=mr_processor,
        cli_log_masker=cli_log_masker,
        db_session_factory=db_session_factory,
    )

    # ------------------------------------------------------------------
    # ConsumerWorker 起動（ブロッキング処理を executor で実行）
    # ------------------------------------------------------------------
    worker = ConsumerWorker(
        rabbitmq_client=rabbitmq_client,
        task_processor=task_processor,
    )

    # ------------------------------------------------------------------
    # SIGTERM / SIGINT ハンドラ登録（グレースフルシャットダウン）
    # シグナル受信時: RabbitMQ の consume ループを停止し、
    # 処理中のタスクが完了してから run_in_executor が戻るのを待つ
    # ------------------------------------------------------------------
    def _handle_signal(sig, frame) -> None:
        """SIGTERM / SIGINT を受信したときのシグナルハンドラ。"""
        request_shutdown()
        logger.info(
            "Consumer: シグナル %s を受信しました。グレースフルシャットダウンを開始します。",
            signal.Signals(sig).name,
        )
        worker.shutdown()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    logger.info("Consumer を起動します")
    loop = asyncio.get_event_loop()
    # RabbitMQ のブロッキング consume をスレッド executor で実行
    # shutdown() が呼ばれると start_consuming() が戻り、ここで await が完了する
    await loop.run_in_executor(None, worker.start)
    logger.info("Consumer: タスク処理完了。プロセスを終了します。")


if __name__ == "__main__":
    asyncio.run(main())
