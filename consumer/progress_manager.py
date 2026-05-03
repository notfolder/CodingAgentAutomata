"""
CLI 標準出力バッファ管理・GitLab コメント作成/更新モジュール。

CLI 実行中に非同期タスクで PROGRESS_REPORT_INTERVAL_SEC 秒ごとに
MR の 1 つのコメントを作成または更新し続ける。
"""

import asyncio
import html
import json
import logging
from datetime import datetime
from typing import Optional

from shared.shutdown_state import is_shutdown_requested

# ロガーを設定
logger = logging.getLogger(__name__)


_MAX_CONSECUTIVE_UPDATE_FAILURES = 3


def _is_executor_shutdown_error(exc: Exception) -> bool:
    """default executor の停止後に submit した失敗かどうかを判定する。"""
    if not isinstance(exc, RuntimeError):
        return False
    return "cannot schedule new futures after shutdown" in str(exc).lower()


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
        # GitLab コメント更新の連続失敗回数
        self._consecutive_update_failures: int = 0

        # stream-json デコード用の状態変数
        # text ブロック（content_block_start type=text）の処理中フラグ
        self._stream_in_text_block: bool = False
        # text ブロック内で累積中のテキスト
        self._stream_text_buffer: str = ""
        # thinking_delta を既にバッファに追加したかどうか（1ブロック1行に制限）
        self._stream_thinking_shown: bool = False
        # 現在処理中のツール名（content_block_start type=tool_use で設定）
        self._stream_current_tool: Optional[str] = None

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

    def _append_to_buffer(self, line: str) -> None:
        """
        1行をバッファに追加する（内部用）。

        BUFFER_MAX_LINES を超過した場合は最も古い行を破棄する。

        Args:
            line: 追加する1行
        """
        self._buffer.append(line)
        if len(self._buffer) > self._buffer_max_lines:
            self._buffer.pop(0)

    def decode_stream_json_line(self, line: str) -> None:
        """
        Claude Code の --output-format stream-json 出力行をデコードしてバッファに追加する。

        stream-json 形式（JSON Lines）の場合は内容に応じてバッファを操作する。
        JSON でない行（opencode 等の通常テキスト）はそのままバッファに追加する。

        対応しているイベント:
        - system/api_retry          : [APIリトライ中... (attempt/max)] を表示
        - stream_event/content_block_start (text)     : テキストブロック開始を検知
        - stream_event/content_block_start (thinking) : thinking ブロック開始を検知
        - stream_event/content_block_start (tool_use) : [ツール呼び出し: name] を追加
        - stream_event/content_block_delta (text_delta)     : [返答中...] を表示しテキストを累積
        - stream_event/content_block_delta (thinking_delta) : [思考中...] を1回だけ追加
        - stream_event/content_block_stop (textブロック完了) : 累積テキストをバッファに追加
        - stream_event/content_block_stop (tool_useブロック完了) : [完了: name] を追加
        - assistant (stop_reason あり) : text/tool_use ブロックを整形して追加
        - result/success             : [完了] を追加
        - result/error               : [エラー] を追加

        Args:
            line: CLI 出力の 1 行
        """
        # JSON でない行はそのまま追加する（opencode 等の通常テキスト出力）
        stripped = line.strip()
        if not stripped.startswith("{"):
            self.append_line(line)
            return

        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            # JSON パース失敗はそのまま追加する
            self.append_line(line)
            return

        event_type: str = obj.get("type", "")

        # ----- system イベント -----
        if event_type == "system":
            subtype: str = obj.get("subtype", "")
            if subtype == "api_retry":
                attempt = obj.get("attempt", "?")
                max_retries = obj.get("max_retries", "?")
                self._append_to_buffer(f"[APIリトライ中... ({attempt}/{max_retries})]")
            # api_retry 以外（init 等）はスキップ
            return

        # ----- stream_event -----
        if event_type == "stream_event":
            event = obj.get("event", {})
            block_event_type: str = event.get("type", "")

            # content_block_start: ブロック種別に応じて状態を更新
            if block_event_type == "content_block_start":
                content_block = event.get("content_block", {})
                cb_type: str = content_block.get("type", "")
                if cb_type == "text":
                    self._stream_in_text_block = True
                    self._stream_text_buffer = ""
                    self._stream_thinking_shown = False
                elif cb_type == "thinking":
                    self._stream_thinking_shown = False
                elif cb_type == "tool_use":
                    self._stream_current_tool = content_block.get("name", "unknown")
                    self._append_to_buffer(f"[ツール呼び出し: {self._stream_current_tool}]")
                return

            # content_block_delta: delta の種別ごとに処理
            if block_event_type == "content_block_delta":
                delta = event.get("delta", {})
                delta_type: str = delta.get("type", "")
                if delta_type == "text_delta":
                    text_chunk: str = delta.get("text", "")
                    self._stream_text_buffer += text_chunk
                    # バッファの末尾に [返答中...] がなければ追加する
                    # （複数の text_delta にわたって1行のみ保持）
                    if not self._buffer or self._buffer[-1] != "[返答中...]":
                        self._append_to_buffer("[返答中...]")
                elif delta_type == "thinking_delta":
                    # [思考中...] は thinking ブロック開始後に1回だけ追加する
                    if not self._stream_thinking_shown:
                        self._stream_thinking_shown = True
                        self._append_to_buffer("[思考中...]")
                # input_json_delta（ツール引数の断片）はスキップ
                return

            # content_block_stop: ブロック完了処理
            if block_event_type == "content_block_stop":
                if self._stream_in_text_block:
                    # text ブロック完了 → 累積テキストをバッファに追加し [返答中...] を除去
                    self._stream_in_text_block = False
                    accumulated: str = self._stream_text_buffer.strip()
                    self._stream_text_buffer = ""
                    # 末尾の [返答中...] を除去する
                    if self._buffer and self._buffer[-1] == "[返答中...]":
                        self._buffer.pop()
                    # 累積テキストを行単位でバッファに追加する
                    if accumulated:
                        for t_line in accumulated.splitlines():
                            if t_line.strip():
                                self._append_to_buffer(t_line)
                elif self._stream_current_tool:
                    # tool_use ブロック完了 → [完了: name] を追加
                    tool_name: str = self._stream_current_tool
                    self._stream_current_tool = None
                    self._append_to_buffer(f"[完了: {tool_name}]")
                return

            # その他の stream_event（message_start, message_delta 等）はスキップ
            return

        # ----- assistant メッセージ -----
        if event_type == "assistant":
            message = obj.get("message", {})
            # stop_reason が null の部分メッセージはスキップ
            if message.get("stop_reason") is None:
                return
            # stop_reason がある最終メッセージ: text / tool_use ブロックを整形して追加
            parts: list[str] = []
            for block in message.get("content", []):
                block_type: str = block.get("type", "")
                if block_type == "text":
                    text = block.get("text", "").strip()
                    if text:
                        parts.append(text)
                elif block_type == "tool_use":
                    parts.append(f"[ツール呼び出し: {block.get('name', 'unknown')}]")
            if parts:
                self.append_line("\n".join(parts))
            return

        # ----- result -----
        if event_type == "result":
            subtype = obj.get("subtype", "")
            if subtype == "success":
                result_text: str = obj.get("result", "").strip()
                self._append_to_buffer(f"[完了] {result_text}" if result_text else "[完了]")
            elif subtype == "error":
                error_text: str = obj.get("error", "").strip()
                self._append_to_buffer(f"[エラー] {error_text}" if error_text else "[エラー]")
            return

        # その他の type はスキップ


    def append_line(self, line: str) -> None:
        """
        バッファに行を追加する。

        複数行テキスト（改行含む）が渡された場合は行単位に分割して追加する。
        BUFFER_MAX_LINES を超過した場合は最も古い行を破棄する。

        Args:
            line: 追加する行テキスト（複数行可）
        """
        # 改行で分割して 1 要素 = 1 表示行に正規化
        for single_line in line.splitlines():
            self._buffer.append(single_line)
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
            self._consecutive_update_failures = 0
        except Exception as exc:
            if _is_executor_shutdown_error(exc):
                self._running = False
                logger.warning(
                    "ProgressManager: executor 停止を検知したため進捗更新を停止します: %s",
                    exc,
                )
                return

            self._consecutive_update_failures += 1
            if self._consecutive_update_failures >= _MAX_CONSECUTIVE_UPDATE_FAILURES:
                self._running = False
                logger.warning(
                    "ProgressManager: コメント更新失敗が %d 回連続したため進捗更新を停止します: %s",
                    self._consecutive_update_failures,
                    exc,
                )
                return

            logger.warning(
                "ProgressManager: コメント更新失敗（%d/%d、継続）: %s",
                self._consecutive_update_failures,
                _MAX_CONSECUTIVE_UPDATE_FAILURES,
                exc,
            )

    @staticmethod
    def _escape_html(text: str) -> str:
        """
        HTML 特殊文字をエスケープする。

        GitLab の <pre> ブロック内でそのまま表示するため、
        &, <, > を HTML エンティティに変換する。

        Args:
            text: エスケープ対象テキスト

        Returns:
            str: エスケープ済みテキスト
        """
        return html.escape(text)

    def _build_comment_body(self) -> str:
        """
        GitLab コメント本文を構築する。

        直近 SUMMARY_LINES 行を <pre> ブロックで本文冒頭に表示し（折りたたみなし）、
        全体ログを <details> + <pre> で折りたたみ表示する。
        バッファが空の場合は「処理中...」を直近エリアに表示する。

        Returns:
            str: コメント本文（Markdown/HTML）
        """
        now_str: str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not self._buffer:
            # バッファが空の場合は処理中メッセージを表示
            body: str = (
                f"直近の出力\n\n"
                f"<pre>処理中...</pre>\n\n"
                f"<details>\n"
                f"<summary>全体ログ（最終更新: {now_str}）</summary>\n\n"
                f"<pre>CLI を実行中です。しばらくお待ちください...</pre>\n\n"
                f"</details>"
            )
            return body

        # 直近ログ: 末尾 SUMMARY_LINES 行を HTML エスケープして表示
        recent_lines: list[str] = self._buffer[-self._summary_lines :]
        recent_text: str = self._escape_html("\n".join(recent_lines))

        # 全体ログ: バッファ全行を HTML エスケープして表示
        full_text: str = self._escape_html("\n".join(self._buffer))

        body = (
            f"直近の出力\n\n"
            f"<pre>{recent_text}</pre>\n\n"
            f"<details>\n"
            f"<summary>全体ログ（最終更新: {now_str}）</summary>\n\n"
            f"<pre>{full_text}</pre>\n\n"
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
