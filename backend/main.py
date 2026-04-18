"""
Backend エントリーポイント（完全版）。

FastAPI アプリケーションを定義し、起動時に Alembic マイグレーションを自動実行する。
全ルーターを /api プレフィックスで登録し、CORS設定・ヘルスチェックを提供する。
"""

import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 設定: 全オリジン許可（フロントエンドからのリクエストを受け付けるため）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全ルーターを /api プレフィックスで登録
# インポートはモジュールレベルで行い、sys.path 設定後に実行されるよう遅延インポートを回避
from backend.routers import auth, cli_adapters, settings, tasks, users  # noqa: E402

app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
app.include_router(cli_adapters.router, prefix="/api")
app.include_router(settings.router, prefix="/api")


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
