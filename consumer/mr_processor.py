"""
F-4: MR 処理の実装モジュール。

MR に対して CLI を実行し、進捗報告・アサイニー監視を並行実行する。
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Callable, Optional
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from shared.models.db import Task, User

logger = logging.getLogger(__name__)


class MRProcessor:
    """F-4 処理: MR 処理を実行するクラス。"""

    def __init__(
        self,
        gitlab_client,
        cli_container_manager,
        cli_adapter_resolver,
        progress_manager_factory,
        prompt_builder,
        virtual_key_service,
        settings,
        db_session_factory: Callable[[], Session],
    ) -> None:
        self._gitlab_client = gitlab_client
        self._cli_container_manager = cli_container_manager
        self._cli_adapter_resolver = cli_adapter_resolver
        self._progress_manager_factory = progress_manager_factory
        self._prompt_builder = prompt_builder
        self._virtual_key_service = virtual_key_service
        self._settings = settings
        self._db_session_factory: Callable[[], Session] = db_session_factory

    def _get_user(self, username: str) -> Optional[User]:
        with self._db_session_factory() as session:
            user: Optional[User] = (
                session.query(User).filter(User.username == username).first()
            )
            if user is None:
                return None
            session.expunge(user)
            return user

    def _update_task_status(
        self,
        task_uuid: str,
        status: str,
        cli_log: Optional[str] = None,
        error_message: Optional[str] = None,
        cli_type: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        with self._db_session_factory() as session:
            task: Optional[Task] = (
                session.query(Task).filter(Task.task_uuid == task_uuid).first()
            )
            if task is None:
                logger.error("MRProcessor: task_uuid='%s' が見つかりません", task_uuid)
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
            if cli_type is not None:
                task.cli_type = cli_type
            if model is not None:
                task.model = model
            session.commit()

    def _build_mcp_config(self, user: User) -> str:
        mcp_config: dict = {}
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
                        logger.warning("MRProcessor: system_mcp_config の JSON パースに失敗")
        if user.user_mcp_config:
            mcp_config.update(user.user_mcp_config)
        return json.dumps(mcp_config, ensure_ascii=False)

    def _build_clone_url(self, project_info: dict, pat: str) -> str:
        """PAT を埋め込んだ git clone 用 URL を構築する（プロトコル://oauth2:PAT@ホスト/パス）。"""
        http_url: str = project_info.get("http_url_to_repo", "")
        parsed = urlparse(http_url)
        # oauth2:PAT@host 形式で URL を再構築
        clone_url: str = (
            f"{parsed.scheme}://oauth2:{pat}@{parsed.netloc}{parsed.path}"
        )
        return clone_url

    def _parse_agent_override(self, description: str) -> dict[str, str]:
        """
        MR description の `agent:` 行から CLI/モデル上書き指定を解析する。

        例: "agent: cli=opencode model=gpt-4o"
        Returns: {"cli": "opencode", "model": "gpt-4o"} (存在するキーのみ)
        """
        override: dict[str, str] = {}
        if not description:
            return override
        # agent: 行を検索
        match = re.search(r"^agent:\s*(.+)$", description, re.MULTILINE | re.IGNORECASE)
        if not match:
            return override
        agent_line: str = match.group(1)
        # key=value ペアを抽出
        for kv_match in re.finditer(r"(\w+)=(\S+)", agent_line):
            key: str = kv_match.group(1).lower()
            value: str = kv_match.group(2)
            if key in ("cli", "model"):
                override[key] = value
        return override

    async def _monitor_assignees(self, project_id: int, mr_iid: int) -> bool:
        """
        PROGRESS_REPORT_INTERVAL_SEC 秒ごとに MR のアサイニーを確認して
        bot がアサイニーから外れたら True を返す。

        Args:
            project_id: GitLab プロジェクト ID
            mr_iid: MR の IID

        Returns:
            bool: bot がアサイニーから外れた場合 True
        """
        bot_name: str = self._settings.gitlab_bot_name
        interval: int = self._settings.progress_report_interval_sec
        loop = asyncio.get_event_loop()

        while True:
            await asyncio.sleep(interval)
            try:
                mr: Optional[dict] = await loop.run_in_executor(
                    None,
                    lambda: self._gitlab_client.get_merge_request(project_id, mr_iid),
                )
                if mr is None:
                    logger.warning("MRProcessor._monitor_assignees: MR が見つかりません")
                    return False
                assignees: list[dict] = mr.get("assignees", [])
                assignee_usernames: list[str] = [
                    a.get("username", "") for a in assignees
                ]
                if bot_name not in assignee_usernames:
                    logger.info(
                        "MRProcessor._monitor_assignees: bot がアサイニーから外れました mr_iid=%d",
                        mr_iid,
                    )
                    return True
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "MRProcessor._monitor_assignees: アサイニー確認失敗（無視）: %s", exc
                )

    async def process(
        self,
        task_uuid: str,
        project_id: int,
        mr_iid: int,
        username: str,
    ) -> None:
        """
        F-4 フロー全体を実行する。

        1. Virtual Key 取得（最初のレビュアー → なければ author）
        2. MR に処理中ラベル付与
        3. MR description の `agent:` 行解析（CLI/モデル上書き）
        4. プロンプト生成（PromptBuilder）
        5. CLI コンテナ起動（PAT を埋め込んだ URL で git clone・ブランチチェックアウト）
        6. MR に処理開始コメント投稿
        7. CLI 実行・ProgressManager 起動・アサイニー監視の並行実行（asyncio.gather）
        8. bot アサイン解除検知時: CLI プロセス強制終了・git push・コンテナ破棄・コメント投稿
        9. タイムアウト処理（CLI_EXEC_TIMEOUT_SEC 秒）
        10. 正常完了・異常終了後の後処理
        11. CLILogMasker で PAT マスク後に cli_log を DB 保存
        """
        self._update_task_status(task_uuid, "running")
        container_id: Optional[str] = None
        cli_log_lines: list[str] = []
        cli_id_used: Optional[str] = None
        model_used: Optional[str] = None

        try:
            # ==========================================
            # ステップ 1: Virtual Key 取得
            # ==========================================
            mr: Optional[dict] = self._gitlab_client.get_merge_request(project_id, mr_iid)
            if mr is None:
                raise ValueError(f"MR #{mr_iid} が見つかりません。")

            # 最初のレビュアーのユーザー名を取得
            reviewers: list[dict] = mr.get("reviewers", [])
            target_username: str = (
                reviewers[0].get("username", "") if reviewers else ""
            )
            if not target_username:
                # レビュアーがいない場合は author を使用
                target_username = mr.get("author", {}).get("username", username)

            user: Optional[User] = self._get_user(target_username)
            if user is None:
                # フォールバック: 渡された username を使用
                user = self._get_user(username)
            if user is None:
                error_msg = f"ユーザーがシステムに登録されていません。"
                self._gitlab_client.create_merge_request_note(
                    project_id, mr_iid, f"❌ エラー: {error_msg}"
                )
                self._update_task_status(task_uuid, "failed", error_message=error_msg)
                return
            if not user.is_active:
                error_msg = f"ユーザー '{user.username}' は無効化されています。"
                self._gitlab_client.create_merge_request_note(
                    project_id, mr_iid, f"❌ エラー: {error_msg}"
                )
                self._update_task_status(task_uuid, "failed", error_message=error_msg)
                return

            virtual_key: str = self._virtual_key_service.decrypt(user.virtual_key_encrypted)

            # ==========================================
            # ステップ 2: MR に処理中ラベル付与
            # ==========================================
            current_labels: list[str] = mr.get("labels", [])
            self._gitlab_client.update_merge_request_labels(
                project_id,
                mr_iid,
                list(set(current_labels + [self._settings.gitlab_processing_label])),
            )

            # ==========================================
            # ステップ 3: agent: 行解析（CLI/モデル上書き）
            # ==========================================
            override: dict[str, str] = self._parse_agent_override(
                mr.get("description", "") or ""
            )
            cli_id_used = override.get("cli", user.default_cli)
            model_used = override.get("model", user.default_model)

            # ==========================================
            # ステップ 4: プロンプト生成
            # ==========================================
            mr_notes: list[dict] = self._gitlab_client.get_merge_request_notes(
                project_id, mr_iid
            )
            mr_comments: str = "\n\n".join(
                [n.get("body", "") for n in mr_notes if n.get("body")]
            )
            branch_name: str = mr.get("source_branch", "")
            project_info: Optional[dict] = self._gitlab_client.get_project_info(project_id)
            repository_url: str = (
                project_info.get("http_url_to_repo", "") if project_info else ""
            )

            prompt: str = self._prompt_builder.build_f4_prompt(
                mr_description=mr.get("description", "") or "",
                mr_comments=mr_comments,
                branch_name=branch_name,
                repository_url=repository_url,
                user_f4_template=user.f4_prompt_template,
            )

            # ==========================================
            # ステップ 5: CLI コンテナ起動・git clone + checkout
            # ==========================================
            from shared.models.db import CLIAdapter
            adapter: Optional[CLIAdapter] = self._cli_adapter_resolver.resolve(cli_id_used)
            if adapter is None:
                raise ValueError(f"CLI アダプタ '{cli_id_used}' が見つかりません。")

            mcp_config: str = self._build_mcp_config(user)
            env_info: dict = {
                "llm_api_key": virtual_key,
                "llm_base_url": self._settings.litellm_proxy_url,
                "prompt": prompt,
                "model": model_used,
                "mcp_config": mcp_config,
            }
            env_vars: dict[str, str] = self._cli_adapter_resolver.build_env_vars(
                adapter, env_info
            )
            start_command: str = self._cli_adapter_resolver.build_start_command(
                adapter, env_info
            )

            # コンテナを起動（初期コマンドは sleep infinity でコンテナを常時起動状態に保つ）
            container_name: str = f"cli-exec-{cli_id_used}-{task_uuid}"
            container_id = self._cli_container_manager.start_container(
                container_name=container_name,
                image=adapter.container_image,
                env_vars=env_vars,
                command="sleep infinity",
            )
            logger.info("MRProcessor: コンテナ起動 container_id=%s", container_id)

            # PAT を埋め込んだ URL で git clone
            clone_url: str = self._build_clone_url(
                project_info or {}, self._settings.gitlab_pat
            )
            clone_exit, clone_out = self._cli_container_manager.exec_command(
                container_id,
                f"git clone {clone_url} /workspace",
            )
            if clone_exit != 0:
                raise ValueError(f"git clone 失敗（exit={clone_exit}）: {clone_out}")

            # ブランチをチェックアウト
            checkout_exit, checkout_out = self._cli_container_manager.exec_command(
                container_id,
                f"cd /workspace && git checkout {branch_name}",
            )
            if checkout_exit != 0:
                raise ValueError(
                    f"git checkout 失敗（exit={checkout_exit}）: {checkout_out}"
                )
            logger.info("MRProcessor: git clone + checkout 完了 branch=%s", branch_name)

            # ==========================================
            # ステップ 6: MR に処理開始コメント投稿
            # ==========================================
            self._gitlab_client.create_merge_request_note(
                project_id,
                mr_iid,
                f"🤖 CLI 処理を開始しました。\n\nCLI: `{cli_id_used}` / モデル: `{model_used}`",
            )

            # ==========================================
            # ステップ 7: CLI 実行・ProgressManager・アサイニー監視を並行実行
            # ==========================================
            progress_manager = self._progress_manager_factory(
                project_id=project_id,
                mr_iid=mr_iid,
            )

            loop = asyncio.get_event_loop()
            bot_removed_flag: list[bool] = [False]
            cli_exit_code_holder: list[int] = [-1]

            async def _run_cli() -> None:
                """CLI コマンドをコンテナ内で実行し、stdout ストリームを ProgressManager に流す。"""
                nonlocal cli_log_lines
                import docker as _docker

                def _exec_stream():
                    """同期的に exec_run でストリームを取得する。"""
                    c = self._cli_container_manager._client.containers.get(container_id)
                    result = c.exec_run(
                        cmd=["/bin/sh", "-c", f"cd /workspace && {start_command}"],
                        stdout=True,
                        stderr=True,
                        stream=True,
                        demux=False,
                    )
                    return result

                exec_result = await loop.run_in_executor(None, _exec_stream)

                # ストリームから行を読み取ってバッファに蓄積
                def _read_lines():
                    for chunk in exec_result.output:
                        if not chunk:
                            continue
                        text = chunk.decode("utf-8", errors="replace")
                        for line in text.splitlines():
                            cli_log_lines.append(line)
                            progress_manager.append_line(line)

                await loop.run_in_executor(None, _read_lines)
                cli_exit_code_holder[0] = exec_result.exit_code or 0

            async def _run_progress() -> None:
                """進捗更新ループを起動する（ProgressManager._update_loop を直接実行）。"""
                progress_manager._running = True
                await progress_manager._update_loop()

            async def _run_monitor() -> bool:
                """アサイニー監視を実行する。"""
                result = await self._monitor_assignees(project_id, mr_iid)
                bot_removed_flag[0] = result
                return result

            # タイムアウト付きで並行実行
            timeout_sec: int = self._settings.cli_exec_timeout_sec

            cli_task = asyncio.create_task(_run_cli())
            progress_task = asyncio.create_task(_run_progress())
            monitor_task = asyncio.create_task(_run_monitor())

            try:
                # CLI タスクの完了 or タイムアウトを待つ
                await asyncio.wait_for(cli_task, timeout=timeout_sec)
                # CLI 完了後、他のタスクをキャンセル
                progress_manager.stop()
                monitor_task.cancel()
                progress_task.cancel()

                # タスクの終了を待つ
                for t in [progress_task, monitor_task]:
                    try:
                        await t
                    except (asyncio.CancelledError, Exception):
                        pass

            except asyncio.TimeoutError:
                # ==========================================
                # ステップ 9: タイムアウト処理
                # ==========================================
                logger.warning("MRProcessor: CLI タイムアウト task_uuid=%s", task_uuid)
                progress_manager.stop()
                cli_task.cancel()
                monitor_task.cancel()
                progress_task.cancel()
                for t in [cli_task, progress_task, monitor_task]:
                    try:
                        await t
                    except (asyncio.CancelledError, Exception):
                        pass

                # タイムアウト前に git push を試みる
                try:
                    self._cli_container_manager.exec_command(
                        container_id, "cd /workspace && git push --set-upstream origin HEAD"
                    )
                except Exception:
                    pass

                timeout_msg = f"CLI 実行がタイムアウトしました（{timeout_sec}秒）。"
                self._gitlab_client.create_merge_request_note(
                    project_id, mr_iid, f"⏰ {timeout_msg}"
                )
                raise TimeoutError(timeout_msg)

            # ==========================================
            # ステップ 8: bot アサイン解除検知時の処理
            # ==========================================
            if bot_removed_flag[0]:
                logger.info("MRProcessor: bot がアサイニーから外れました。CLI を強制終了します。")
                # CLI プロセスを強制終了
                process_name: str = cli_id_used or "cli"
                pid: Optional[int] = self._cli_container_manager.get_container_pid(
                    container_id, process_name
                )
                if pid:
                    self._cli_container_manager.kill_process(container_id, pid)

                # git push を実行（失敗は無視）
                try:
                    self._cli_container_manager.exec_command(
                        container_id,
                        "cd /workspace && git push --set-upstream origin HEAD",
                    )
                except Exception:
                    pass

                unassign_msg = "🛑 bot がアサイニーから外されたため、処理を中断しました。変更内容を push しました。"
                self._gitlab_client.create_merge_request_note(
                    project_id, mr_iid, unassign_msg
                )
                raise RuntimeError("bot がアサイニーから外されました。")

            # ==========================================
            # ステップ 10: 正常完了の後処理
            # ==========================================
            exit_code: int = cli_exit_code_holder[0]
            if exit_code != 0:
                raise RuntimeError(f"CLI が非ゼロ終了コードで終了しました: exit_code={exit_code}")

            # 最終進捗を flush
            await progress_manager.flush()

            # 完了コメント・ラベル更新
            done_labels: list[str] = [
                lbl
                for lbl in current_labels
                if lbl != self._settings.gitlab_processing_label
            ]
            done_labels.append(self._settings.gitlab_done_label)
            self._gitlab_client.update_merge_request_labels(
                project_id, mr_iid, list(set(done_labels))
            )
            self._gitlab_client.create_merge_request_note(
                project_id, mr_iid, "✅ CLI 処理が完了しました。"
            )

            # ==========================================
            # ステップ 11: CLILogMasker で PAT マスク後に cli_log を DB 保存
            # ==========================================
            from consumer.cli_log_masker import CLILogMasker
            masker = CLILogMasker()
            raw_log: str = "\n".join(cli_log_lines)
            masked_log: str = masker.mask(raw_log)

            self._update_task_status(
                task_uuid,
                "completed",
                cli_log=masked_log,
                cli_type=cli_id_used,
                model=model_used,
            )
            logger.info("MRProcessor: F-4 処理完了 task_uuid=%s", task_uuid)

        except Exception as exc:
            error_msg: str = str(exc)
            logger.error(
                "MRProcessor: F-4 処理失敗 task_uuid=%s: %s",
                task_uuid,
                error_msg,
                exc_info=True,
            )
            # GitLab MR にエラーコメント投稿
            try:
                self._gitlab_client.create_merge_request_note(
                    project_id,
                    mr_iid,
                    f"❌ F-4 処理中にエラーが発生しました。\n\n```\n{error_msg}\n```",
                )
                # 処理中ラベルを削除
                mr_current: Optional[dict] = self._gitlab_client.get_merge_request(
                    project_id, mr_iid
                )
                if mr_current:
                    restore_labels: list[str] = [
                        lbl
                        for lbl in mr_current.get("labels", [])
                        if lbl != self._settings.gitlab_processing_label
                    ]
                    self._gitlab_client.update_merge_request_labels(
                        project_id, mr_iid, restore_labels
                    )
            except Exception as gitlab_exc:
                logger.warning("MRProcessor: GitLab エラーコメント投稿失敗（無視）: %s", gitlab_exc)

            # PAT マスク処理してログを保存
            try:
                from consumer.cli_log_masker import CLILogMasker
                masker = CLILogMasker()
                raw_log = "\n".join(cli_log_lines)
                masked_log = masker.mask(raw_log)
            except Exception:
                masked_log = "\n".join(cli_log_lines)

            self._update_task_status(
                task_uuid,
                "failed",
                cli_log=masked_log,
                error_message=error_msg,
                cli_type=cli_id_used,
                model=model_used,
            )

        finally:
            # コンテナ即時破棄
            if container_id:
                try:
                    self._cli_container_manager.exec_command(
                        container_id,
                        "cd /workspace && git push --set-upstream origin HEAD 2>/dev/null || true",
                    )
                except Exception:
                    pass
                self._cli_container_manager.stop_container(container_id)
                logger.info("MRProcessor: コンテナを破棄しました container_id=%s", container_id)
