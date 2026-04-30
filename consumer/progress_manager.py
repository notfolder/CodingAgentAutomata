"""
CLI 標準出力バッファ管理・GitLab コメント作成/更新モジュール。

CLI 実行中に非同期タスクで PROGRESS_REPORT_INTERVAL_SEC 秒ごとに
MR の 1 つのコメントを作成または更新し続ける。
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from shared.shutdown_state import is_shutdown_requested

# ロガーを設定
logger = logging.getLogger(__name__)


class ProgressManager:
    """
    CLI 実行中の進捗を GitLab MR コメントに定期更新するクラス。

    バッファに蓄積した CLI 標準出力を <details> 形式で MR コメントに投稿する。
    コメントは 1 つのコメントを作成・更新し続ける（新規作成はしない）。

    進捗コメントの形式:
        <details>
        <summary>進捗状況（最終更新: {更新日時}）

        {直近 SUMMARY_LINES 行}
        </summary>

        {全体出力（最大 BUFFER_MAX_LINES 行）}

        </details>
    """

    def __init__(
        self,
        gitlab_client,
        project_id: int,
        mr_iid: int,
        interval_sec: int,
        summary_lines: int,
        buffer_max_lines: int,
    ) -> None:
        """
        初期化。

        Args:
            gitlab_client: GitLabClient インスタンス
            project_id: GitLab プロジェクト ID
            mr_iid: MR の IID
            interval_sec: 進捗更新間隔（秒）
            summary_lines: summary に表示する末尾行数
            buffer_max_lines: バッファの最大行数（超過分は古い行を破棄）
        """
        self._gitlab_client = gitlab_client
        self._project_id: int = project_id
        self._mr_iid: int = mr_iid
        self._interval_sec: int = interval_sec
        self._summary_lines: int = summary_lines
        self._buffer_max_lines: int = buffer_max_lines

        # 標準出力バッファ
        self._buffer: list[str] = []
        # 作成済みコメントの Note ID（None の場合はまだ作成していない）
        self._note_id: Optional[int] = None
        # 更新ループの実行フラグ
        self._running: bool = False
        # 更新タスク
        self._update_task: Optional[asyncio.Task] = None

    async def start(self, stdout_stream) -> None:
        """
        非同期タスクで進捗更新ループを開始する。

        stdout_stream から行を読み取りながら、INTERVAL 秒ごとに GitLab コメントを更新する。
        ストリームが終了したら更新ループを停止する。

        Args:
            stdout_stream: コンテナの標準出力ストリーム（バイト列イテレータ）
        """
        self._running = True
        # 定期更新ループをバックグラウンドタスクとして起動
        self._update_task = asyncio.create_task(self._update_loop())

        try:
            loop = asyncio.get_event_loop()
            # ストリームをブロッキング I/O として executor で処理
            await loop.run_in_executor(None, self._read_stream, stdout_stream)
        finally:
            # ストリーム終了後、更新ループを停止
            self.stop()
            if self._update_task and not self._update_task.done():
                # 更新ループが終了するのを待つ（最大 interval_sec 秒）
                try:
                    await asyncio.wait_for(self._update_task, timeout=self._interval_sec)
                except asyncio.TimeoutError:
                    self._update_task.cancel()

    def _read_stream(self, stdout_stream) -> None:
        """
        ストリームから行を読み取ってバッファに追加する（同期処理）。

        Args:
            stdout_stream: コンテナの標準出力ストリーム
        """
        for chunk in stdout_stream:
            if not chunk:
                continue
            # バイト列をデコードして行ごとに分割
            text: str = chunk.decode("utf-8", errors="replace")
            for line in text.splitlines():
                self.append_line(line)

    def append_line(self, line: str) -> None:
        """
        バッファに 1 行追加する。

        BUFFER_MAX_LINES を超過した場合は最も古い行を破棄する。

        Args:
            line: 追加する行テキスト
        """
        self._buffer.append(line)
        # バッファ上限超過時は先頭（最古）の行を削除
        if len(self._buffer) > self._buffer_max_lines:
            self._buffer.pop(0)

    async def _update_loop(self) -> None:
        """
        INTERVAL 秒ごとに GitLab コメントを更新するループ。

        self._running が False になるまでループし続ける。
        """
        while self._running and not is_shutdown_requested():
            # INTERVAL 秒待機（細かく分割して停止フラグを確認）
            for _ in range(self._interval_sec * 2):
                if not self._running or is_shutdown_requested():
                    break
                await asyncio.sleep(0.5)
            if is_shutdown_requested():
                break
            # 停止フラグが立っていても最後の更新は行う
            # バッファが空でも「処理中...」コメントを投稿して CLI が動作中であることを示す
            await self._post_or_update()

    async def _post_or_update(self) -> None:
        """
        GitLab コメントを作成または更新する。

        _note_id が None の場合は新規作成し、それ以外は既存コメントを更新する。
        バッファが空の場合は「処理中...」メッセージを投稿する。
        """
        if is_shutdown_requested():
            return

        body: str = self._build_comment_body()
        loop = asyncio.get_event_loop()

        try:
            if self._note_id is None:
                # 初回: 新規コメントを作成
                result = await loop.run_in_executor(
                    None,
                    lambda: self._gitlab_client.create_merge_request_note(
                        self._project_id, self._mr_iid, body
                    ),
                )
                if result:
                    self._note_id = result.get("id")
                    logger.debug(
                        "ProgressManager: 進捗コメントを作成しました note_id=%s",
                        self._note_id,
                    )
            else:
                # 2 回目以降: 既存コメントを更新
                await loop.run_in_executor(
                    None,
                    lambda: self._gitlab_client.update_merge_request_note(
                        self._project_id, self._mr_iid, self._note_id, body
                    ),
                )
                logger.debug(
                    "ProgressManager: 進捗コメントを更新しました note_id=%s",
                    self._note_id,
                )
        except Exception as exc:
            # コメント更新失敗はログ記録のみ（処理継続）
            logger.warning("ProgressManager: コメント更新失敗（無視）: %s", exc)

    def _build_comment_body(self) -> str:
        """
        GitLab コメント本文を構築する。

        <details> 形式でサマリー（直近 SUMMARY_LINES 行）と
        全体出力（最大 BUFFER_MAX_LINES 行）を含む。
        バッファが空の場合は「処理中...」メッセージを表示する。

        Returns:
            str: コメント本文（Markdown）
        """
        now_str: str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not self._buffer:
            # バッファが空の場合は処理中メッセージを表示
            body: str = (
                f"<details>\n"
                f"<summary>進捗状況（最終更新: {now_str}）\n\n"
                f"処理中...\n"
                f"</summary>\n\n"
                f"CLI を実行中です。しばらくお待ちください...\n\n"
                f"</details>"
            )
            return body

        # サマリー: 直近 SUMMARY_LINES 行
        summary_text: str = "\n".join(self._buffer[-self._summary_lines :])

        # 全体出力: バッファ全行
        full_text: str = "\n".join(self._buffer)

        body = (
            f"<details>\n"
            f"<summary>進捗状況（最終更新: {now_str}）\n\n"
            f"{summary_text}\n"
            f"</summary>\n\n"
            f"{full_text}\n\n"
            f"</details>"
        )
        return body

    def stop(self) -> None:
        """
        更新ループを停止する。

        _running フラグを False にして次のループで終了させる。
        """
        self._running = False

    async def flush(self) -> None:
        """
        最後の進捗コメントを GitLab に更新する。

        CLI 終了後に呼び出して最終状態をコメントに反映する。
        """
        self.stop()
        if is_shutdown_requested():
            return
        if self._buffer:
            await self._post_or_update()
