"""
システム設定リポジトリモジュール。

system_settings テーブルへのデータアクセス処理を担当する。
key-value 形式の設定の取得・更新（upsert）を提供する。
"""

from typing import Optional

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from shared.models.db import SystemSetting


class SystemSettingsRepository:
    """system_settings テーブルへのアクセスを担当するリポジトリクラス。"""

    def __init__(self, db: Session) -> None:
        """
        初期化。

        Args:
            db: SQLAlchemy データベースセッション
        """
        self._db = db

    def get(self, key: str) -> Optional[SystemSetting]:
        """
        キーでシステム設定を取得する。

        Args:
            key: 取得対象の設定キー

        Returns:
            SystemSetting | None: 見つかった場合はSystemSettingオブジェクト、なければNone
        """
        return (
            self._db.query(SystemSetting)
            .filter(SystemSetting.key == key)
            .first()
        )

    def get_all(self) -> list[SystemSetting]:
        """
        全システム設定を取得する。

        Returns:
            list[SystemSetting]: システム設定一覧
        """
        return self._db.query(SystemSetting).all()

    def set(self, key: str, value: str) -> SystemSetting:
        """
        システム設定を登録または更新する（upsert）。

        Args:
            key: 設定キー
            value: 設定値（文字列またはJSON文字列）

        Returns:
            SystemSetting: 登録/更新後のSystemSettingオブジェクト
        """
        setting = self.get(key)
        if setting:
            # 既存設定を更新
            setting.value = value
        else:
            # 新規設定を登録
            setting = SystemSetting(key=key, value=value)
            self._db.add(setting)
        self._db.commit()
        self._db.refresh(setting)
        return setting

    def upsert_many(self, settings: dict[str, str]) -> None:
        """
        複数のシステム設定を一括で登録または更新する。

        None 値は除外してスキップする。

        Args:
            settings: {設定キー: 設定値} の辞書
        """
        for key, value in settings.items():
            if value is not None:
                self.set(key, value)
