"""
SQLAlchemy ORM モデル定義モジュール。

データベーステーブルのモデルを定義する：
- User: システムユーザー情報・Virtual Key（暗号化）・CLI設定
- CLIAdapter: CLIアダプタ設定
- Task: タスク実行履歴
- SystemSetting: システム設定（プロンプトテンプレート等）
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    LargeBinary,
    Text,
    UUID as SAUUID,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.database import Base


class CLIAdapter(Base):
    """
    CLIアダプタ設定テーブル（cli_adapters）。

    CLIエージェントの起動コマンドテンプレート・環境変数マッピング等を管理する。
    is_builtin=True のアダプタは管理画面から削除不可。
    """

    __tablename__ = "cli_adapters"

    # CLIエージェント識別子（例: claude, opencode）- 主キー
    cli_id: Mapped[str] = mapped_column(primary_key=True, nullable=False)

    # cli-execコンテナイメージ名・タグ
    container_image: Mapped[str] = mapped_column(nullable=False)

    # 起動コマンドテンプレート（{prompt}/{model}/{mcp_config}変数含む）
    start_command_template: Mapped[str] = mapped_column(Text, nullable=False)

    # 情報名→環境変数名マッピング（JSONB）
    env_mappings: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # 設定内容をJSON環境変数で渡す場合の環境変数名
    config_content_env: Mapped[Optional[str]] = mapped_column(nullable=True)

    # 組み込みアダプタフラグ（True は削除不可）
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # 登録日時（自動設定）
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    # 最終更新日時（更新時に自動設定）
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now()
    )

    # リレーション: このアダプタをデフォルトに設定しているユーザー
    users: Mapped[list["User"]] = relationship("User", back_populates="cli_adapter")

    # リレーション: このアダプタを使用したタスク
    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="cli_adapter_rel")


class User(Base):
    """
    システムユーザーテーブル（users）。

    GitLabユーザーと紐づくシステムユーザー情報を管理する。
    Virtual Key は AES-256-GCM で暗号化して保存する。
    """

    __tablename__ = "users"

    # GitLabユーザー名（主キー）
    username: Mapped[str] = mapped_column(primary_key=True, nullable=False)

    # メールアドレス（ユニーク）
    email: Mapped[str] = mapped_column(unique=True, nullable=False)

    # AES-256-GCM暗号化済みVirtual Key
    virtual_key_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    # デフォルトCLIエージェントID（cli_adapters.cli_id 参照）
    default_cli: Mapped[str] = mapped_column(
        ForeignKey("cli_adapters.cli_id"), nullable=False
    )

    # デフォルトLLMモデル名
    default_model: Mapped[str] = mapped_column(nullable=False)

    # 権限ロール（admin または user）
    role: Mapped[str] = mapped_column(
        nullable=False,
        # CHECK制約: admin または user のみ許可
    )

    # 有効/無効フラグ（デフォルト: True）
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # bcryptハッシュ化パスワード
    password_hash: Mapped[str] = mapped_column(nullable=False)

    # システムMCP設定の適用オン/オフ（デフォルト: True）
    system_mcp_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # ユーザー個別MCP設定（NULL=適用なし）
    user_mcp_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # ユーザー個別F-4プロンプトテンプレート（NULL=システム設定使用）
    f4_prompt_template: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 登録日時（自動設定）
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    # 最終更新日時（更新時に自動設定）
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now()
    )

    # テーブル制約: role は admin または user のみ
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'user')", name="users_role_check"),
    )

    # リレーション: デフォルトCLIアダプタ
    cli_adapter: Mapped["CLIAdapter"] = relationship("CLIAdapter", back_populates="users")

    # リレーション: このユーザーのタスク一覧
    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="user")


class Task(Base):
    """
    タスク実行履歴テーブル（tasks）。

    Issue/MR処理の実行状態・CLIログ・エラー情報を記録する。
    重複処理防止のための部分ユニーク制約は Alembic マイグレーションで作成する。
    """

    __tablename__ = "tasks"

    # タスク一意識別子（UUID v4）- 主キー
    task_uuid: Mapped[str] = mapped_column(
        SAUUID(as_uuid=False), primary_key=True, nullable=False
    )

    # タスク種別（issue または merge_request）
    task_type: Mapped[str] = mapped_column(nullable=False)

    # GitLabプロジェクトID
    gitlab_project_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Issue IIDまたはMR IID
    source_iid: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # 実行対象ユーザー名（users.username 参照）
    username: Mapped[str] = mapped_column(ForeignKey("users.username"), nullable=False)

    # ステータス（pending/running/completed/failed）
    status: Mapped[str] = mapped_column(nullable=False)

    # 使用したCLIエージェントID（cli_adapters.cli_id 参照）
    cli_type: Mapped[Optional[str]] = mapped_column(
        ForeignKey("cli_adapters.cli_id"), nullable=True
    )

    # 使用したモデル名
    model: Mapped[Optional[str]] = mapped_column(nullable=True)

    # CLIの実行ログ（標準出力・エラー出力）
    cli_log: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # エラー内容（失敗時のみ）
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # タスク作成日時（自動設定）
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    # 処理開始日時
    started_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    # 処理完了日時
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    # テーブル制約
    __table_args__ = (
        CheckConstraint(
            "task_type IN ('issue', 'merge_request')",
            name="tasks_task_type_check",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="tasks_status_check",
        ),
        # 注意: 部分ユニーク制約 tasks_no_duplicate_active は
        # Alembic マイグレーション（001_initial.py）で CREATE UNIQUE INDEX として作成する
    )

    # リレーション: タスクを実行したユーザー
    user: Mapped["User"] = relationship("User", back_populates="tasks")

    # リレーション: 使用したCLIアダプタ
    cli_adapter_rel: Mapped[Optional["CLIAdapter"]] = relationship(
        "CLIAdapter", back_populates="tasks"
    )


class SystemSetting(Base):
    """
    システム設定テーブル（system_settings）。

    F-3/F-4プロンプトテンプレート・システムMCP設定等を key-value 形式で管理する。

    主要なキー:
        - f3_prompt_template: F-3（Issue→MR変換）用プロンプトテンプレート
        - f4_prompt_template: F-4（MR処理）用プロンプトテンプレート（システムデフォルト）
        - system_mcp_config: システムMCP設定（JSON文字列）
    """

    __tablename__ = "system_settings"

    # 設定キー（主キー）
    key: Mapped[str] = mapped_column(primary_key=True, nullable=False)

    # 設定値（テンプレート文字列またはJSON文字列）
    value: Mapped[str] = mapped_column(Text, nullable=False)

    # 最終更新日時（更新時に自動設定）
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now()
    )
