"""
SQLAlchemy データベースセッション管理モジュール。

DATABASE_URL 環境変数から接続文字列を取得し、
SQLAlchemy の Engine・Session・Base を提供する。
FastAPI の依存性注入用ジェネレータ get_db() を定義する。
"""

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# 環境変数から接続URLを取得（未設定の場合はフォールバック値を使用）
_DATABASE_URL: str = os.environ.get(
    "DATABASE_URL",
    "postgresql://user:password@postgresql:5432/db",
)

# SQLAlchemy エンジンを生成
# pool_pre_ping=True: 接続プールのヘルスチェックを有効化
engine = create_engine(_DATABASE_URL, pool_pre_ping=True)

# セッションファクトリを生成
# autocommit=False: トランザクションを明示的にコミット/ロールバックする
# autoflush=False: flush タイミングを手動制御する
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """
    全 ORM モデルの基底クラス。

    SQLAlchemy 2.0 スタイルの DeclarativeBase を継承する。
    """
    pass


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI 依存性注入用のデータベースセッションジェネレータ。

    リクエストごとにセッションを生成し、処理終了後に自動的にクローズする。
    例外発生時もセッションを確実にクローズするよう try/finally を使用する。

    Yields:
        Session: SQLAlchemy データベースセッション

    Usage:
        @app.get("/items")
        def read_items(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
