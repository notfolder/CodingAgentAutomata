"""
アプリケーション設定モジュール。

pydantic-settings を使用して環境変数から設定値を読み込む。
.env ファイルも自動的に読み込む（存在する場合）。
"""

import logging

from pydantic_settings import BaseSettings, SettingsConfigDict

# ロガーを設定
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """
    アプリケーション全体の設定クラス。

    環境変数または .env ファイルから設定値を読み込む。
    全フィールドはデフォルト値を持ち、必須フィールドは None チェックで使用前に検証すること。
    """

    model_config = SettingsConfigDict(
        # .env ファイルが存在する場合に読み込む
        env_file=".env",
        env_file_encoding="utf-8",
        # 未定義の環境変数は無視する
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # GitLab 接続設定
    # ------------------------------------------------------------------
    # GitLab Personal Access Token（api スコープ必須）
    gitlab_pat: str = ""

    # GitLab インスタンスのベースURL
    gitlab_api_url: str = "https://gitlab.com"

    # GitLab上のBotアカウントのユーザー名
    gitlab_bot_name: str = ""

    # タスク処理対象を識別するラベル名
    gitlab_bot_label: str = "coding agent"

    # 処理中状態を示すラベル名
    gitlab_processing_label: str = "coding agent processing"

    # 処理完了状態を示すラベル名
    gitlab_done_label: str = "coding agent done"

    # ------------------------------------------------------------------
    # LiteLLM Proxy 設定
    # ------------------------------------------------------------------
    # LiteLLM Proxy のベースURL
    litellm_proxy_url: str = "http://litellm:4000"

    # ------------------------------------------------------------------
    # データベース設定
    # ------------------------------------------------------------------
    # PostgreSQL接続URL
    database_url: str = "postgresql://user:password@postgresql:5432/db"

    # ------------------------------------------------------------------
    # RabbitMQ 設定
    # ------------------------------------------------------------------
    # RabbitMQ 接続URL
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"

    # ------------------------------------------------------------------
    # 暗号化・認証設定
    # ------------------------------------------------------------------
    # AES-256-GCM 暗号化鍵（base64エンコード、32バイト = 256bit）
    encryption_key: str = ""

    # JWT署名シークレットキー
    jwt_secret_key: str = ""

    # ------------------------------------------------------------------
    # Webhook 設定
    # ------------------------------------------------------------------
    # GitLab Webhook の HMAC-SHA256 署名検証シークレット
    gitlab_webhook_secret: str = ""

    # Webhook受信ポート
    webhook_port: int = 8080

    # ------------------------------------------------------------------
    # ポーリング設定
    # ------------------------------------------------------------------
    # GitLab ポーリング間隔（秒）
    polling_interval_seconds: int = 30

    # GitLab ポーリング対象プロジェクトIDのカンマ区切りリスト
    gitlab_project_ids: str = ""

    # ------------------------------------------------------------------
    # 進捗報告設定
    # ------------------------------------------------------------------
    # GitLab MR コメントへの進捗報告間隔（秒）
    progress_report_interval_sec: int = 60

    # 進捗レポートに含めるログ末尾行数
    progress_report_summary_lines: int = 20

    # 進捗ログバッファの最大行数（超えた場合は古い行を破棄）
    progress_report_buffer_max_lines: int = 20000

    # ------------------------------------------------------------------
    # CLI 実行設定
    # ------------------------------------------------------------------
    # CLI 実行タイムアウト（秒）
    cli_exec_timeout_sec: int = 10800


def get_settings() -> Settings:
    """
    アプリケーション設定のシングルトンインスタンスを返す。

    Returns:
        Settings: 設定インスタンス
    """
    return Settings()


def get_project_ids(settings: Settings) -> list[int]:
    """
    gitlab_project_ids 文字列をパースして整数リストで返す。

    空文字列の場合は空リストを返す。

    Args:
        settings: Settings インスタンス

    Returns:
        GitLabプロジェクトIDの整数リスト
    """
    if not settings.gitlab_project_ids.strip():
        return []
    ids: list[int] = []
    for part in settings.gitlab_project_ids.split(","):
        part = part.strip()
        if part:
            try:
                ids.append(int(part))
            except ValueError:
                logger.warning(
                    "get_project_ids: invalid project ID format '%s', skipping", part
                )
    return ids
