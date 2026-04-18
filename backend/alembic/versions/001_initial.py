"""
初期マイグレーション: 全テーブル作成。

作成するテーブル:
- cli_adapters: CLIアダプタ設定
- users: システムユーザー情報・Virtual Key（暗号化）・CLI設定
- tasks: タスク実行履歴
- system_settings: システム設定（プロンプトテンプレート等）

部分ユニーク制約 tasks_no_duplicate_active を tasks テーブルに追加する。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# マイグレーション識別子
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    テーブルを作成し、制約・インデックスを設定する。
    """

    # ------------------------------------------------------------------
    # cli_adapters テーブル作成
    # users テーブルが FK参照するため先に作成する
    # ------------------------------------------------------------------
    op.create_table(
        "cli_adapters",
        # CLIエージェント識別子（主キー）
        sa.Column("cli_id", sa.String(255), primary_key=True, nullable=False),
        # cli-execコンテナイメージ名・タグ
        sa.Column("container_image", sa.String(512), nullable=False),
        # 起動コマンドテンプレート
        sa.Column("start_command_template", sa.Text, nullable=False),
        # 情報名→環境変数名マッピング（JSONB）
        sa.Column("env_mappings", postgresql.JSONB, nullable=False),
        # 設定内容をJSON環境変数で渡す場合の環境変数名
        sa.Column("config_content_env", sa.String(255), nullable=True),
        # 組み込みアダプタフラグ（True は削除不可）
        sa.Column("is_builtin", sa.Boolean, nullable=False, server_default="false"),
        # 登録日時
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        # 最終更新日時
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # ------------------------------------------------------------------
    # users テーブル作成
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        # GitLabユーザー名（主キー）
        sa.Column("username", sa.String(255), primary_key=True, nullable=False),
        # メールアドレス（ユニーク）
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        # AES-256-GCM暗号化済みVirtual Key
        sa.Column("virtual_key_encrypted", sa.LargeBinary, nullable=False),
        # デフォルトCLIエージェントID
        sa.Column(
            "default_cli",
            sa.String(255),
            sa.ForeignKey("cli_adapters.cli_id"),
            nullable=False,
        ),
        # デフォルトLLMモデル名
        sa.Column("default_model", sa.String(255), nullable=False),
        # 権限ロール（admin または user）
        sa.Column("role", sa.String(20), nullable=False),
        # 有効/無効フラグ
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        # bcryptハッシュ化パスワード
        sa.Column("password_hash", sa.String(255), nullable=False),
        # システムMCP設定の適用オン/オフ
        sa.Column("system_mcp_enabled", sa.Boolean, nullable=False, server_default="true"),
        # ユーザー個別MCP設定（NULL=適用なし）
        sa.Column("user_mcp_config", postgresql.JSONB, nullable=True),
        # ユーザー個別F-4プロンプトテンプレート（NULL=システム設定使用）
        sa.Column("f4_prompt_template", sa.Text, nullable=True),
        # 登録日時
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        # 最終更新日時
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        # CHECK制約: role は admin または user のみ
        sa.CheckConstraint("role IN ('admin', 'user')", name="users_role_check"),
    )

    # ------------------------------------------------------------------
    # tasks テーブル作成
    # ------------------------------------------------------------------
    op.create_table(
        "tasks",
        # タスク一意識別子（UUID v4）- 主キー
        sa.Column(
            "task_uuid",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            nullable=False,
        ),
        # タスク種別（issue または merge_request）
        sa.Column("task_type", sa.String(50), nullable=False),
        # GitLabプロジェクトID
        sa.Column("gitlab_project_id", sa.BigInteger, nullable=False),
        # Issue IIDまたはMR IID
        sa.Column("source_iid", sa.BigInteger, nullable=False),
        # 実行対象ユーザー名
        sa.Column(
            "username",
            sa.String(255),
            sa.ForeignKey("users.username"),
            nullable=False,
        ),
        # ステータス
        sa.Column("status", sa.String(20), nullable=False),
        # 使用したCLIエージェントID
        sa.Column(
            "cli_type",
            sa.String(255),
            sa.ForeignKey("cli_adapters.cli_id"),
            nullable=True,
        ),
        # 使用したモデル名
        sa.Column("model", sa.String(255), nullable=True),
        # CLIの実行ログ
        sa.Column("cli_log", sa.Text, nullable=True),
        # エラー内容（失敗時のみ）
        sa.Column("error_message", sa.Text, nullable=True),
        # タスク作成日時
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        # 処理開始日時
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        # 処理完了日時
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        # CHECK制約: task_type は issue または merge_request のみ
        sa.CheckConstraint(
            "task_type IN ('issue', 'merge_request')",
            name="tasks_task_type_check",
        ),
        # CHECK制約: status は pending/running/completed/failed のみ
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="tasks_status_check",
        ),
    )

    # 重複処理防止のための部分ユニーク制約（F-10）
    # gitlab_project_id・source_iid・task_type の組み合わせで
    # status が pending または running の行が1件のみ存在できる
    op.execute(
        """
        CREATE UNIQUE INDEX tasks_no_duplicate_active
        ON tasks (gitlab_project_id, source_iid, task_type)
        WHERE status IN ('pending', 'running')
        """
    )

    # ------------------------------------------------------------------
    # system_settings テーブル作成
    # ------------------------------------------------------------------
    op.create_table(
        "system_settings",
        # 設定キー（主キー）
        sa.Column("key", sa.String(255), primary_key=True, nullable=False),
        # 設定値（テンプレート文字列またはJSON文字列）
        sa.Column("value", sa.Text, nullable=False),
        # 最終更新日時
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )


def downgrade() -> None:
    """
    テーブルを削除する（upgrade の逆順）。
    """
    # 外部キー参照の関係で tasks → users → cli_adapters の順に削除
    op.drop_table("system_settings")
    op.execute("DROP INDEX IF EXISTS tasks_no_duplicate_active")
    op.drop_table("tasks")
    op.drop_table("users")
    op.drop_table("cli_adapters")
