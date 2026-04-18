"""
CLIアダプタリポジトリモジュール。

cli_adapters テーブルへのデータアクセス処理を担当する。
アダプタの取得・作成・更新・削除・ユーザー参照チェックを提供する。
"""

from typing import Optional

from sqlalchemy.orm import Session

from shared.models.db import CLIAdapter, User


class CLIAdapterRepository:
    """cli_adapters テーブルへのアクセスを担当するリポジトリクラス。"""

    def __init__(self, db: Session) -> None:
        """
        初期化。

        Args:
            db: SQLAlchemy データベースセッション
        """
        self._db = db

    def get_all(self) -> list[CLIAdapter]:
        """
        全CLIアダプタを取得する。

        Returns:
            list[CLIAdapter]: CLIアダプタ一覧
        """
        return self._db.query(CLIAdapter).order_by(CLIAdapter.cli_id).all()

    def get_by_id(self, cli_id: str) -> Optional[CLIAdapter]:
        """
        cli_id でCLIアダプタを取得する。

        Args:
            cli_id: 取得対象のCLIアダプタID

        Returns:
            CLIAdapter | None: 見つかった場合はCLIAdapterオブジェクト、なければNone
        """
        return (
            self._db.query(CLIAdapter)
            .filter(CLIAdapter.cli_id == cli_id)
            .first()
        )

    def create(self, adapter: CLIAdapter) -> CLIAdapter:
        """
        CLIアダプタをDBに登録する。

        Args:
            adapter: 登録するCLIAdapterオブジェクト

        Returns:
            CLIAdapter: 登録後のCLIAdapterオブジェクト
        """
        self._db.add(adapter)
        self._db.commit()
        self._db.refresh(adapter)
        return adapter

    def update(self, adapter: CLIAdapter) -> CLIAdapter:
        """
        CLIアダプタ情報を更新する。

        Args:
            adapter: 更新するCLIAdapterオブジェクト（変更済み）

        Returns:
            CLIAdapter: 更新後のCLIAdapterオブジェクト
        """
        self._db.commit()
        self._db.refresh(adapter)
        return adapter

    def delete(self, cli_id: str) -> bool:
        """
        CLIアダプタを削除する。

        Args:
            cli_id: 削除対象のCLIアダプタID

        Returns:
            bool: 削除成功時 True、対象が存在しない場合 False
        """
        adapter = self.get_by_id(cli_id)
        if not adapter:
            return False
        self._db.delete(adapter)
        self._db.commit()
        return True

    def is_referenced_by_users(self, cli_id: str) -> bool:
        """
        指定のCLIアダプタIDをデフォルトCLIとして使用しているユーザーが存在するか確認する。

        Args:
            cli_id: チェック対象のCLIアダプタID

        Returns:
            bool: 参照しているユーザーが存在する場合 True
        """
        return (
            self._db.query(User)
            .filter(User.default_cli == cli_id)
            .first()
        ) is not None
