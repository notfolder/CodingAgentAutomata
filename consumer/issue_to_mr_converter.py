"""
F-3: Issue→MR 変換処理の実装モジュール。

Issue に対して CLI を実行し、ブランチ名・MR タイトルを生成して
GitLab 上に Draft MR を作成する。
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

from sqlalchemy.orm import Session

from shared.models.db import Task, User

# ロガーを設定
logger = logging.getLogger(__name__)


class IssueToMRConverter:
    """
    F-3 処理: Issue→MR 変換を実行するクラス。

    Virtual Key の取得・復号、CLI コンテナの起動・実行、
    GitLab API でのブランチ作成・MR 作成・ラベル管理を担当する。
    """

    def __init__(
        self,
        gitlab_client,
        cli_container_manager,
        cli_adapter_resolver,
        prompt_builder,
        virtual_key_service,
        settings,
        db_session_factory: Callable[[], Session],
    ) -> None:
        """
        初期化。

        Args:
            gitlab_client: GitLabClient インスタンス
            cli_container_manager: CLIContainerManager インスタンス
            cli_adapter_resolver: CLIAdapterResolver インスタンス
            prompt_builder: PromptBuilder インスタンス
            virtual_key_service: VirtualKeyService インスタンス
            settings: Settings インスタンス
            db_session_factory: SQLAlchemy Session ファクトリ関数
        """
        self._gitlab_client = gitlab_client
        self._cli_container_manager = cli_container_manager
        self._cli_adapter_resolver = cli_adapter_resolver
        self._prompt_builder = prompt_builder
        self._virtual_key_service = virtual_key_service
        self._settings = settings
        self._db_session_factory: Callable[[], Session] = db_session_factory

    def _get_user(self, username: str) -> Optional[User]:
        """
        DB からユーザー情報を取得する。

        Args:
            username: GitLab ユーザー名

        Returns:
            User | None: ユーザーオブジェクト、存在しない場合は None
        """
        with self._db_session_factory() as session:
            user: Optional[User] = (
                session.query(User).filter(User.username == username).first()
            )
            if user is None:
                return None
            # セッションを閉じる前にデタッチ
            session.expunge(user)
            return user

    def _update_task_status(
        self,
        task_uuid: str,
        status: str,
        cli_log: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """
        tasks テーブルのタスクステータスを更新する。

        Args:
            task_uuid: タスク UUID
            status: 更新するステータス（completed/failed/running）
            cli_log: CLI ログテキスト（省略可）
            error_message: エラーメッセージ（省略可）
        """
        with self._db_session_factory() as session:
            task: Optional[Task] = (
                session.query(Task).filter(Task.task_uuid == task_uuid).first()
            )
            if task is None:
                logger.error(
                    "IssueToMRConverter: task_uuid='%s' が見つかりません", task_uuid
                )
                return
            task.status = status
            if status == "running":
                task.started_at = datetime.now(timezone.utc)
            elif status in ("completed", "failed"):
                task.completed_at = datetime.now(timezone.utc)
            if cli_log is not None:
                task.cli_log = cli_log
            if error_message is not None:
                task.error_message = error_message
            session.commit()

    def _build_mcp_config(self, user: User) -> str:
        """
        ユーザー設定とシステム設定からMCP設定 JSON 文字列を構築する。

        ユーザーの system_mcp_enabled フラグと user_mcp_config を考慮して
        最終的な MCP 設定を JSON 文字列で返す。

        Args:
            user: ユーザーオブジェクト

        Returns:
            str: MCP 設定の JSON 文字列（設定なしの場合は空 JSON "{}"）
        """
        mcp_config: dict = {}

        # システム MCP 設定を適用（ユーザーフラグが True の場合）
        if user.system_mcp_enabled:
            with self._db_session_factory() as session:
                from shared.models.db import SystemSetting
                setting = (
                    session.query(SystemSetting)
                    .filter(SystemSetting.key == "system_mcp_config")
                    .first()
                )
                if setting and setting.value:
                    try:
                        mcp_config = json.loads(setting.value)
                    except (json.JSONDecodeError, TypeError):
                        logger.warning(
                            "IssueToMRConverter: system_mcp_config の JSON パースに失敗"
                        )

        # ユーザー個別 MCP 設定でマージ（ユーザー設定が優先）
        if user.user_mcp_config:
            mcp_config.update(user.user_mcp_config)

        # Claude Code CLI は {"mcpServers": {...}} 形式を要求するため、mcpServers キーでラップして返す
        return json.dumps({"mcpServers": mcp_config}, ensure_ascii=False)

    def convert(
        self,
        task_uuid: str,
        project_id: int,
        issue_iid: int,
        username: str,
    ) -> None:
        """
        F-3 フロー全体を実行する。

        1. Virtual Key 取得・復号（未登録・無効ユーザーチェック）
        2. Issue に処理中ラベル付与
        3. プロンプト生成（PromptBuilder）
        4. CLI アダプタ解決
        5. CLI コンテナ起動（Virtual Key 環境変数セット）
        6. CLI 実行・標準出力の最終行を JSON パース（branch_name, mr_title 取得）
        7. ブランチ作成
        8. Draft MR 作成（Issue の description を MR description に設定）
        9. Issue の author を MR の最初のレビュアーに設定
        10. Issue のコメントをすべて MR にコピー
        11. Issue に MR 作成完了コメント投稿
        12. Issue の処理中ラベル削除・done ラベル付与・Issue はクローズしない
        13. コンテナ即時破棄
        14. タスクステータス更新（completed/failed）

        Args:
            task_uuid: タスク UUID
            project_id: GitLab プロジェクト ID
            issue_iid: Issue の IID
            username: 処理対象の GitLab ユーザー名
        """
        # タスクを running 状態に更新
        self._update_task_status(task_uuid, "running")
        container_id: Optional[str] = None

        try:
            # ==========================================
            # ステップ 1: Virtual Key 取得・復号
            # ==========================================
            user: Optional[User] = self._get_user(username)
            if user is None:
                error_msg = f"ユーザー '{username}' がシステムに登録されていません。"
                logger.error("IssueToMRConverter: %s", error_msg)
                self._gitlab_client.create_issue_note(
                    project_id, issue_iid, f"❌ エラー: {error_msg}"
                )
                self._update_task_status(task_uuid, "failed", error_message=error_msg)
                return

            if not user.is_active:
                error_msg = f"ユーザー '{username}' は無効化されています。"
                logger.error("IssueToMRConverter: %s", error_msg)
                self._gitlab_client.create_issue_note(
                    project_id, issue_iid, f"❌ エラー: {error_msg}"
                )
                self._update_task_status(task_uuid, "failed", error_message=error_msg)
                return

            virtual_key: str = self._virtual_key_service.decrypt(
                user.virtual_key_encrypted
            )
            logger.debug(
                "IssueToMRConverter: Virtual Key を取得しました username=%s", username
            )

            # ==========================================
            # ステップ 2: Issue に処理中ラベル付与
            # ==========================================
            issue: Optional[dict] = self._gitlab_client.get_issue(
                project_id, issue_iid
            )
            if issue is None:
                error_msg = f"Issue #{issue_iid} が見つかりません。"
                logger.error("IssueToMRConverter: %s", error_msg)
                self._update_task_status(task_uuid, "failed", error_message=error_msg)
                return

            current_labels: list[str] = issue.get("labels", [])
            # 処理中ラベルを追加
            updated_labels: list[str] = list(
                set(current_labels + [self._settings.gitlab_processing_label])
            )
            self._gitlab_client.update_issue_labels(
                project_id, issue_iid, updated_labels
            )
            logger.debug(
                "IssueToMRConverter: 処理中ラベル付与: issue_iid=%d", issue_iid
            )

            # ==========================================
            # ステップ 3: プロンプト生成
            # ==========================================
            # Issue のコメントを取得してテキスト化
            issue_notes: list[dict] = self._gitlab_client.get_issue_notes(
                project_id, issue_iid
            )
            issue_comments: str = "\n\n".join(
                [n.get("body", "") for n in issue_notes if n.get("body")]
            )

            # プロジェクト情報を取得
            project_info: Optional[dict] = self._gitlab_client.get_project_info(
                project_id
            )
            project_name: str = (
                project_info.get("name", str(project_id)) if project_info else str(project_id)
            )
            repository_url: str = (
                project_info.get("http_url_to_repo", "") if project_info else ""
            )

            prompt: str = self._prompt_builder.build_f3_prompt(
                issue_title=issue.get("title", ""),
                issue_description=issue.get("description", "") or "",
                issue_comments=issue_comments,
                project_name=project_name,
                repository_url=repository_url,
            )

            # ==========================================
            # ステップ 4: CLI アダプタ解決
            # ==========================================
            from shared.models.db import CLIAdapter
            adapter: Optional[CLIAdapter] = self._cli_adapter_resolver.resolve(
                user.default_cli
            )
            if adapter is None:
                error_msg = f"CLI アダプタ '{user.default_cli}' が見つかりません。"
                logger.error("IssueToMRConverter: %s", error_msg)
                self._gitlab_client.create_issue_note(
                    project_id, issue_iid, f"❌ エラー: {error_msg}"
                )
                self._update_task_status(task_uuid, "failed", error_message=error_msg)
                return

            # MCP 設定を構築
            mcp_config: str = self._build_mcp_config(user)

            # 環境変数辞書を構築
            env_info: dict = {
                "llm_api_key": virtual_key,
                "llm_base_url": self._settings.litellm_proxy_url,
                "prompt": prompt,
                "model": user.default_model,
                "mcp_config": mcp_config,
            }
            env_vars: dict[str, str] = self._cli_adapter_resolver.build_env_vars(
                adapter, env_info
            )

            # 起動コマンドを構築
            start_command: str = self._cli_adapter_resolver.build_start_command(
                adapter, env_info
            )

            # ==========================================
            # ステップ 5: CLI コンテナ起動
            # ==========================================
            container_name: str = f"cli-exec-{user.default_cli}-{task_uuid}"
            container_id = self._cli_container_manager.start_container(
                container_name=container_name,
                image=adapter.container_image,
                env_vars=env_vars,
                command=start_command,
            )
            logger.info(
                "IssueToMRConverter: コンテナを起動しました container_id=%s", container_id
            )

            # ==========================================
            # ステップ 6: CLI 実行・標準出力の最終行を JSON パース
            # ==========================================
            # コンテナの終了を待つ（ブロッキング）
            import docker
            container = self._cli_container_manager._client.containers.get(
                container_id
            )
            container.wait()

            # 全ログを取得
            raw_logs: bytes = container.logs(stdout=True, stderr=True)
            cli_output: str = raw_logs.decode("utf-8", errors="replace")
            logger.debug(
                "IssueToMRConverter: CLI 出力を取得しました output_len=%d",
                len(cli_output),
            )

            # 最終行を JSON パース（branch_name, mr_title を取得）
            lines: list[str] = [
                line.strip() for line in cli_output.splitlines() if line.strip()
            ]
            if not lines:
                raise ValueError("CLI が出力を生成しませんでした。")

            last_line: str = lines[-1]
            try:
                result_json: dict = json.loads(last_line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"CLI の最終出力が JSON ではありません: '{last_line}'"
                ) from exc

            branch_name: str = result_json.get("branch_name", "")
            mr_title: str = result_json.get("mr_title", "")
            if not branch_name:
                raise ValueError(
                    "CLI の出力に branch_name が含まれていません。"
                )
            if not mr_title:
                raise ValueError(
                    "CLI の出力に mr_title が含まれていません。"
                )
            logger.info(
                "IssueToMRConverter: CLI 結果: branch_name=%s, mr_title=%s",
                branch_name,
                mr_title,
            )

            # ==========================================
            # ステップ 7: ブランチ作成
            # ==========================================
            self._gitlab_client.create_branch(
                project_id=project_id,
                branch_name=branch_name,
                ref="main",
            )
            logger.info(
                "IssueToMRConverter: ブランチを作成しました branch_name=%s", branch_name
            )

            # ==========================================
            # ステップ 8: Draft MR 作成
            # ==========================================
            # Issue の author の GitLab ユーザー情報を取得
            author_username: str = issue.get("author", {}).get("username", "")
            reviewer_ids: list[int] = []
            if author_username:
                author_info: Optional[dict] = self._gitlab_client.get_user_by_username(
                    author_username
                )
                if author_info:
                    reviewer_ids = [author_info.get("id")]

            # Draft MR を作成（Issue の description を MR description に設定）
            mr: Optional[dict] = self._gitlab_client.create_merge_request(
                project_id=project_id,
                title=mr_title,
                source_branch=branch_name,
                target_branch="main",
                description=issue.get("description", "") or "",
                draft=True,
                reviewer_ids=reviewer_ids if reviewer_ids else None,
                label_ids=[self._settings.gitlab_bot_label],
            )
            if mr is None:
                raise ValueError("MR の作成に失敗しました。")

            mr_iid: int = mr.get("iid", 0)
            logger.info(
                "IssueToMRConverter: Draft MR を作成しました mr_iid=%d", mr_iid
            )

            # ==========================================
            # ステップ 9: Issue の author を MR の最初のレビュアーに設定
            # （create_merge_request で reviewer_ids を渡済み）
            # ==========================================

            # ==========================================
            # ステップ 10: Issue のコメントをすべて MR にコピー
            # ==========================================
            for note in issue_notes:
                note_body: str = note.get("body", "")
                if note_body:
                    self._gitlab_client.create_merge_request_note(
                        project_id=project_id,
                        iid=mr_iid,
                        body=f"*(Issueからコピー)*\n\n{note_body}",
                    )
            logger.debug(
                "IssueToMRConverter: Issue コメントを MR にコピーしました 件数=%d",
                len(issue_notes),
            )

            # ==========================================
            # ステップ 11: Issue に MR 作成完了コメント投稿
            # ==========================================
            mr_url: str = mr.get("web_url", "")
            self._gitlab_client.create_issue_note(
                project_id=project_id,
                iid=issue_iid,
                body=(
                    f"✅ Draft MR を作成しました。\n\n"
                    f"MR: {mr_url}\n\n"
                    f"ブランチ: `{branch_name}`"
                ),
            )

            # ==========================================
            # ステップ 12: Issue の処理中ラベル削除・done ラベル付与
            # ==========================================
            final_labels: list[str] = [
                lbl
                for lbl in current_labels
                if lbl != self._settings.gitlab_processing_label
            ]
            final_labels.append(self._settings.gitlab_done_label)
            self._gitlab_client.update_issue_labels(
                project_id, issue_iid, list(set(final_labels))
            )
            logger.debug(
                "IssueToMRConverter: Issue ラベルを更新しました labels=%s", final_labels
            )

            # ==========================================
            # ステップ 14: タスクステータスを completed に更新
            # ==========================================
            self._update_task_status(
                task_uuid,
                "completed",
                cli_log=cli_output,
            )
            logger.info(
                "IssueToMRConverter: F-3 処理完了 task_uuid=%s, mr_iid=%d",
                task_uuid,
                mr_iid,
            )

        except Exception as exc:
            error_msg: str = str(exc)
            logger.error(
                "IssueToMRConverter: F-3 処理失敗 task_uuid=%s: %s",
                task_uuid,
                error_msg,
                exc_info=True,
            )
            # GitLab Issue にエラーコメントを投稿
            try:
                self._gitlab_client.create_issue_note(
                    project_id=project_id,
                    iid=issue_iid,
                    body=f"❌ F-3 処理中にエラーが発生しました。\n\n```\n{error_msg}\n```",
                )
                # 処理中ラベルを削除
                issue_data: Optional[dict] = self._gitlab_client.get_issue(
                    project_id, issue_iid
                )
                if issue_data:
                    labels_to_restore: list[str] = [
                        lbl
                        for lbl in issue_data.get("labels", [])
                        if lbl != self._settings.gitlab_processing_label
                    ]
                    self._gitlab_client.update_issue_labels(
                        project_id, issue_iid, labels_to_restore
                    )
            except Exception as gitlab_exc:
                logger.warning(
                    "IssueToMRConverter: GitLab エラーコメント投稿失敗（無視）: %s",
                    gitlab_exc,
                )
            self._update_task_status(
                task_uuid, "failed", error_message=error_msg
            )

        finally:
            # ==========================================
            # ステップ 13: コンテナ即時破棄
            # ==========================================
            if container_id:
                self._cli_container_manager.stop_container(container_id)
                logger.info(
                    "IssueToMRConverter: コンテナを破棄しました container_id=%s",
                    container_id,
                )
