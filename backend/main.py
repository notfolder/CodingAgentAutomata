"""
Backend エントリーポイント（暫定版）。

FastAPI アプリケーションを定義し、起動時に Alembic マイグレーションを自動実行する。
現時点では /health エンドポイントのみ実装している。
"""

import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

# ロガーを設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# shared モジュールを Python パスに追加する
# backend コンテナ内では /app/shared に shared パッケージが配置される
_shared_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "shared"))
_app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for _path in (_shared_path, _app_path):
    if _path not in sys.path:
        sys.path.insert(0, _path)


def run_migrations() -> None:
    """
    Alembic マイグレーションをアプリケーション起動時に自動実行する。

    alembic.ini を基準ディレクトリとして使用し、
    head リビジョンまで全てのマイグレーションを適用する。
    マイグレーション失敗時はエラーログを出力して例外を再送出する。
    """
    import alembic.config
    from alembic import command

    # alembic.ini のパスを設定（backend ディレクトリ内に配置）
    alembic_cfg_path = os.path.join(os.path.dirname(__file__), "alembic.ini")
    alembic_cfg = alembic.config.Config(alembic_cfg_path)

    # スクリプトの場所を絶対パスで指定
    alembic_cfg.set_main_option(
        "script_location",
        os.path.join(os.path.dirname(__file__), "alembic"),
    )

    # DATABASE_URL 環境変数から接続URLを取得して設定を上書き
    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://user:password@postgresql:5432/db",
    )
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    logger.info("Alembicマイグレーションを実行します: head")
    command.upgrade(alembic_cfg, "head")
    logger.info("Alembicマイグレーション完了")


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """
    アプリケーションのライフサイクル管理コンテキストマネージャ。

    起動時: Alembic マイグレーションを自動実行する。
    マイグレーション失敗時はアプリケーション起動を中断する。

    Args:
        application: FastAPI アプリケーションインスタンス
    """
    logger.info("アプリケーション起動中...")
    try:
        run_migrations()
    except Exception as exc:
        logger.error("マイグレーション失敗: %s", exc, exc_info=True)
        # マイグレーション失敗時はアプリを起動しない
        raise
    # アプリケーション実行中
    yield
    # シャットダウン処理（現時点では特になし）
    logger.info("アプリケーション終了")


# FastAPI アプリケーションインスタンスを生成
app = FastAPI(
    title="CodingAgentAutomata Backend",
    description="GitLab自律コーディングエージェントシステムの管理API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check() -> dict:
    """
    ヘルスチェックエンドポイント。

    アプリケーションが正常に動作しているかを確認するためのエンドポイント。
    docker-compose の healthcheck にも使用できる。

    Returns:
        dict: ステータス情報
    """
    return {"status": "ok"}
