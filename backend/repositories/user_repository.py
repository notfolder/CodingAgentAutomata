"""
ユーザーリポジトリモジュール。

users テーブルへのデータアクセス処理を担当する。
ユーザーの取得・作成・更新・削除・メール重複チェックを提供する。
"""

from typing import Optional

from sqlalchemy.orm import Session

from shared.models.db import User


class UserRepository:
    """users テーブルへのアクセスを担当するリポジトリクラス。"""

    def __init__(self, db: Session) -> None:
        """
        初期化。

        Args:
            db: SQLAlchemy データベースセッション
        """
        self._db = db

    def get_by_username(self, username: str) -> Optional[User]:
        """
        ユーザー名でユーザーを取得する。

        Args:
            username: 取得対象のユーザー名

        Returns:
            User | None: 見つかった場合はUserオブジェクト、なければNone
        """
        return self._db.query(User).filter(User.username == username).first()

    def get_all(
        self,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[list[User], int]:
        """
        ユーザー一覧を取得する。

        Args:
            search: username の前方一致検索文字列（省略可）
            skip: スキップ件数（ページネーション用）
            limit: 取得件数上限

        Returns:
            tuple[list[User], int]: ユーザーリストと総件数のタプル
        """
        query = self._db.query(User)

        # username の前方一致フィルタ
        if search:
            query = query.filter(User.username.like(f"{search}%"))

        # 総件数を取得
        total: int = query.count()

        # ページネーション適用
        users = query.order_by(User.username).offset(skip).limit(limit).all()

        return users, total

    def create(self, user: User) -> User:
        """
        ユーザーをDBに登録する。

        Args:
            user: 登録するUserオブジェクト

        Returns:
            User: 登録後のUserオブジェクト
        """
        self._db.add(user)
        self._db.commit()
        self._db.refresh(user)
        return user

    def update(self, user: User) -> User:
        """
        ユーザー情報を更新する。

        Args:
            user: 更新するUserオブジェクト（変更済み）

        Returns:
            User: 更新後のUserオブジェクト
        """
        self._db.commit()
        self._db.refresh(user)
        return user

    def delete(self, username: str) -> bool:
        """
        ユーザーを削除する。

        Args:
            username: 削除対象のユーザー名

        Returns:
            bool: 削除成功時 True、対象が存在しない場合 False
        """
        user = self.get_by_username(username)
        if not user:
            return False
        self._db.delete(user)
        self._db.commit()
        return True

    def email_exists(
        self,
        email: str,
        exclude_username: Optional[str] = None,
    ) -> bool:
        """
        指定メールアドレスが既に登録されているか確認する。

        Args:
            email: チェック対象のメールアドレス
            exclude_username: 除外するユーザー名（更新時に自分自身を除外するため）

        Returns:
            bool: 既に存在する場合 True
        """
        query = self._db.query(User).filter(User.email == email)
        if exclude_username:
            query = query.filter(User.username != exclude_username)
        return query.first() is not None
