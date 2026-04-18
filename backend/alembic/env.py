"""
Alembic 環境設定ファイル。

DATABASE_URL 環境変数から接続文字列を取得し、
shared/models/db.py の Base を使用してオートマイグレーションを設定する。
"""

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# alembic.ini のロガー設定を適用
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# shared モジュールを Python パスに追加する
# backend コンテナ内では /app/shared に shared パッケージが配置される
_shared_path = os.path.join(os.path.dirname(__file__), "..", "..", "shared")
_app_path = os.path.join(os.path.dirname(__file__), "..", "..")
for _path in (_shared_path, _app_path):
    _abs = os.path.abspath(_path)
    if _abs not in sys.path:
        sys.path.insert(0, _abs)

# shared.models.db の Base をインポートしてメタデータを使用する
from shared.models.db import Base  # noqa: E402

# Alembic がテーブル差分を検出するためのメタデータ
target_metadata = Base.metadata

# DATABASE_URL 環境変数から接続URLを取得して alembic.ini の値を上書きする
_db_url = os.environ.get(
    "DATABASE_URL",
    "postgresql://user:password@postgresql:5432/db",
)
config.set_main_option("sqlalchemy.url", _db_url)


def run_migrations_offline() -> None:
    """
    オフラインモード（URL のみ）でマイグレーションを実行する。

    DB接続なしで SQL スクリプトを生成する場合に使用する。
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    オンラインモード（実際の DB 接続）でマイグレーションを実行する。

    アプリケーション起動時の自動マイグレーションに使用する。
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # マイグレーション時は接続プールを使用しない
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


# オフライン / オンライン どちらのモードで実行するかを判定
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
