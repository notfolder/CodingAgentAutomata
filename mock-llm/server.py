"""
モック LLM サーバー
OpenAI 互換 API と LiteLLM Proxy Virtual Key 管理 API の両方をエミュレートする。
E2E テスト環境で実際の OpenAI / Anthropic API キーなしに動作させるためのモック。
"""

import json
import logging
import os
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PORT = int(os.environ.get("PORT", "4000"))

# 発行済みキーの一覧（メモリ内管理）
issued_keys: dict[str, dict] = {}


class MockLLMHandler(BaseHTTPRequestHandler):
    """モック LLM サーバーのリクエストハンドラー"""

    def log_message(self, format: str, *args) -> None:
        """アクセスログを Python logging に転送する"""
        logger.info("REQUEST %s %s", self.path, args[0] if args else "")

    def _send_json(self, code: int, data: dict) -> None:
        """JSON レスポンスを送信する"""
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        """リクエストボディを JSON としてパースする"""
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    # -------------------------------------------------------------------------
    # OpenAI 互換エンドポイント
    # -------------------------------------------------------------------------

    def _handle_chat_completions(self) -> None:
        """POST /v1/chat/completions — ダミー応答を返す"""
        body = self._read_body()
        messages = body.get("messages", [])
        
        # F-3 テンプレート用: branch_name / mr_title を含む JSON を返す
        branch_suffix = uuid.uuid4().hex[:8]
        
        # すべてのユーザーメッセージを集める（Claude CLIは複数回APIを呼ぶため）
        all_user_content = " ".join(
            m["content"] for m in messages 
            if m.get("role") == "user" and isinstance(m.get("content"), str)
        )
        
        # F-3テンプレートを検出: "ブランチ名" と "MRタイトル" の両方を含む場合
        is_f3_template = "ブランチ名" in all_user_content and "MRタイトル" in all_user_content
        
        if is_f3_template:
            content = (
                'ブランチ名とMRタイトルを生成しました。\n'
                f'{{"branch_name": "feature/mock-{branch_suffix}", '
                '"mr_title": "Draft: Mock implementation"}}'
            )
        else:
            content = "Mock LLM response: task completed successfully."

        self._send_json(200, {
            "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": body.get("model", "gpt-4o"),
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        })

    def _handle_models(self) -> None:
        """GET /v1/models — 利用可能なモデル一覧を返す"""
        self._send_json(200, {
            "object": "list",
            "data": [
                {"id": "gpt-4o", "object": "model", "created": 1706037612, "owned_by": "openai"},
                {"id": "claude-opus-4-5", "object": "model", "created": 1706037612, "owned_by": "anthropic"},
                {"id": "openai/gpt-4o", "object": "model", "created": 1706037612, "owned_by": "openai"},
            ],
        })

    # -------------------------------------------------------------------------
    # LiteLLM Proxy 互換エンドポイント
    # -------------------------------------------------------------------------

    def _handle_key_generate(self) -> None:
        """POST /key/generate — ダミー Virtual Key を発行する"""
        body = self._read_body()
        alias = body.get("key_alias", "default")
        new_key = f"sk-mock-{uuid.uuid4().hex[:16]}"
        issued_keys[new_key] = {"alias": alias, "models": body.get("models", [])}
        logger.info("Virtual Key 発行: alias=%s key=%s...", alias, new_key[:16])
        self._send_json(200, {
            "key": new_key,
            "key_alias": alias,
            "models": body.get("models", []),
            "token": new_key,
        })

    def _handle_key_info(self) -> None:
        """GET /key/info — キー情報を返す"""
        self._send_json(200, {"key": "mock", "models": ["gpt-4o", "claude-opus-4-5"]})

    def _handle_health(self) -> None:
        """GET /health — ヘルスチェック"""
        self._send_json(200, {"status": "healthy", "litellm_version": "mock-1.0.0"})

    # -------------------------------------------------------------------------
    # Anthropic 互換エンドポイント
    # -------------------------------------------------------------------------

    def _handle_messages(self) -> None:
        """POST /v1/messages — Anthropic 形式のダミー応答を返す（SSE ストリーミング対応）"""
        body = self._read_body()
        messages = body.get("messages", [])

        # 最初のユーザーメッセージを取得して F-3 か F-4 かを判定する
        first_user = next(
            (
                m["content"] if isinstance(m["content"], str)
                else (m["content"][0].get("text", "") if isinstance(m["content"], list) else "")
                for m in messages if m.get("role") == "user"
            ),
            "",
        )

        # F-3 テンプレート用: branch_name / mr_title を含む JSON を返す
        # F-3 プロンプトには 'branch_name' キーや "ブランチ名" / "MRタイトル" が含まれる
        branch_suffix = uuid.uuid4().hex[:8]
        is_f3 = (
            "branch_name" in first_user
            or "ブランチ名" in first_user
            or "MRタイトル" in first_user
        )
        print(
            f"[mock-llm] is_f3={is_f3} "
            f"first_user_len={len(first_user)} "
            f"first_user_snippet={first_user[:120]!r}",
            flush=True,
        )
        if is_f3:
            content = (
                'ブランチ名とMRタイトルを生成しました。\n'
                f'{{"branch_name": "feature/mock-{branch_suffix}", '
                '"mr_title": "Draft: Mock implementation"}'
            )
            # F-3 は遅延なし
            event_delay = 0.0
        else:
            # F-4 (MR処理): テスト用に各 SSE イベント間に遅延を入れ、CLI が十分な時間実行されるようにする
            # PROGRESS_REPORT_INTERVAL_SEC=5 の 2 サイクル（10秒）より長く実行させることで
            # T-30 の bot アサイン解除検知テストが正常動作する
            content = "Mock LLM response: task completed successfully."
            event_delay = 2.0

        stream = body.get("stream", False)
        msg_id = f"msg_{uuid.uuid4().hex[:8]}"
        model = body.get("model", "claude-opus-4-5")

        if stream:
            # SSE ストリーミング応答 (Anthropic SDK が期待する形式)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()

            def sse(event: str, data: dict) -> bytes:
                line = f"event: {event}\ndata: {json.dumps(data)}\n\n"
                return line.encode("utf-8")

            events = [
                sse("message_start", {
                    "type": "message_start",
                    "message": {
                        "id": msg_id,
                        "type": "message",
                        "role": "assistant",
                        "content": [],
                        "model": model,
                        "stop_reason": None,
                        "stop_sequence": None,
                        "usage": {"input_tokens": 100, "output_tokens": 0},
                    },
                }),
                sse("content_block_start", {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "text", "text": ""},
                }),
                sse("ping", {"type": "ping"}),
                sse("content_block_delta", {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": content},
                }),
                sse("content_block_stop", {
                    "type": "content_block_stop",
                    "index": 0,
                }),
                sse("message_delta", {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                    "usage": {"input_tokens": 100, "output_tokens": 50},
                }),
                sse("message_stop", {"type": "message_stop"}),
            ]
            for chunk in events:
                self.wfile.write(chunk)
                self.wfile.flush()
                if event_delay > 0:
                    time.sleep(event_delay)
        else:
            self._send_json(200, {
                "id": msg_id,
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": content}],
                "model": model,
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 100, "output_tokens": 50},
            })

    # -------------------------------------------------------------------------
    # ルーティング
    # -------------------------------------------------------------------------

    def do_GET(self) -> None:
        """GET リクエストをルーティングする"""
        if self.path == "/health" or self.path == "/healthz":
            self._handle_health()
        elif self.path.startswith("/v1/models"):
            self._handle_models()
        elif self.path.startswith("/key/info"):
            self._handle_key_info()
        else:
            self._send_json(404, {"error": f"Not found: {self.path}"})

    def do_POST(self) -> None:
        """POST リクエストをルーティングする"""
        if self.path in ("/v1/chat/completions", "/chat/completions"):
            self._handle_chat_completions()
        elif self.path.startswith("/v1/messages"):
            self._handle_messages()
        elif self.path == "/key/generate":
            self._handle_key_generate()
        elif self.path == "/key/delete":
            self._send_json(200, {"deleted_keys": []})
        else:
            # 未知のエンドポイントは 200 で空レスポンスを返す（柔軟性のため）
            body = self._read_body()
            logger.warning("未知のエンドポイント: POST %s body=%s", self.path, body)
            self._send_json(200, {"status": "ok"})


def main() -> None:
    """モック LLM サーバーを起動する"""
    server = HTTPServer(("0.0.0.0", PORT), MockLLMHandler)
    logger.info("モック LLM サーバーを起動しました: port=%d", PORT)
    logger.info("エンドポイント:")
    logger.info("  GET  /health             ヘルスチェック")
    logger.info("  GET  /v1/models          モデル一覧")
    logger.info("  POST /v1/chat/completions チャット補完")
    logger.info("  POST /key/generate       Virtual Key 発行")
    server.serve_forever()


if __name__ == "__main__":
    main()
