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
RESPONSE_DELAY_SEC = float(os.environ.get("MOCK_LLM_RESPONSE_DELAY_SEC", "0"))

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
            # F-3 は consumer 側が行単位JSONを逆順探索するため、JSON文字列のみ返す
            content = json.dumps(
                {
                    "branch_name": f"feature/mock-{branch_suffix}",
                    "mr_title": "Draft: Mock implementation",
                },
                ensure_ascii=False,
            )
        else:
            # F-4 用: 設定された遅延を入れる
            if RESPONSE_DELAY_SEC > 0:
                time.sleep(RESPONSE_DELAY_SEC)
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

        # すべてのユーザーメッセージを連結して F-3 か F-4 かを判定する
        # Claude CLI は複数回 API を呼ぶため first_user だけでは取りこぼす
        user_texts: list[str] = []
        for m in messages:
            if m.get("role") != "user":
                continue
            content = m.get("content")
            if isinstance(content, str):
                user_texts.append(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and isinstance(item.get("text"), str):
                        user_texts.append(item["text"])
        all_user_content = "\n".join(user_texts)

        # F-3 テンプレート用: branch_name / mr_title を含む JSON を返す
        # F-3 プロンプトには 'branch_name' キーや "ブランチ名" / "MRタイトル" が含まれる
        branch_suffix = uuid.uuid4().hex[:8]
        is_f3 = (
            "branch_name" in all_user_content
            or "ブランチ名" in all_user_content
            or "MRタイトル" in all_user_content
        )
        print(
            f"[mock-llm] is_f3={is_f3} "
            f"all_user_len={len(all_user_content)} "
            f"all_user_snippet={all_user_content[:120]!r}",
            flush=True,
        )
        if is_f3:
            # F-3 は consumer 側が行単位JSONを逆順探索するため、JSON文字列のみ返す
            content = json.dumps(
                {
                    "branch_name": f"feature/mock-{branch_suffix}",
                    "mr_title": "Draft: Mock implementation",
                },
                ensure_ascii=False,
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
            self.send_header("Connection", "close")
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
        elif self.path.startswith("/responses/") or self.path.startswith("/v1/responses/"):
            # Responses API の GET（ID 指定）は 404 を返す（opencode は使用しないが念のため）
            self._send_json(404, {"error": "Not found"})
        else:
            self._send_json(404, {"error": f"Not found: {self.path}"})

    def _handle_responses(self) -> None:
        """POST /responses — OpenAI Responses API 互換のダミー応答を返す（SSE ストリーミング対応）"""
        body = self._read_body()

        # リクエストから input テキストを取得（F-3 / F-4 の判定に使用）
        input_data = body.get("input", "")
        if isinstance(input_data, list):
            # input が配列の場合はテキストを連結
            input_texts = []
            for item in input_data:
                if isinstance(item, dict):
                    content = item.get("content", "")
                    if isinstance(content, str):
                        input_texts.append(content)
                    elif isinstance(content, list):
                        for c in content:
                            if isinstance(c, dict) and c.get("type") == "input_text":
                                input_texts.append(c.get("text", ""))
            all_input = " ".join(input_texts)
        elif isinstance(input_data, str):
            all_input = input_data
        else:
            all_input = ""

        # instructions も合わせて F-3 判定に使用
        instructions = body.get("instructions", "") or ""
        all_text = all_input + " " + instructions

        # F-3 検出: branch_name / ブランチ名 / MRタイトル を含む場合
        branch_suffix = uuid.uuid4().hex[:8]
        is_f3 = (
            "branch_name" in all_text
            or "ブランチ名" in all_text
            or "MRタイトル" in all_text
        )

        if is_f3:
            content = json.dumps(
                {
                    "branch_name": f"feature/mock-{branch_suffix}",
                    "mr_title": "Draft: Mock implementation",
                },
                ensure_ascii=False,
            )
            event_delay = 0.0
        else:
            # F-4 用: テスト用に遅延を入れる
            if RESPONSE_DELAY_SEC > 0:
                time.sleep(RESPONSE_DELAY_SEC)
            content = "Mock LLM response: task completed successfully."
            event_delay = 0.0

        resp_id = f"resp_{uuid.uuid4().hex[:24]}"
        msg_id = f"msg_{uuid.uuid4().hex[:8]}"
        model = body.get("model", "gpt-4o")
        created_at = int(time.time())

        stream = body.get("stream", False)

        response_base = {
            "id": resp_id,
            "object": "response",
            "created_at": created_at,
            "status": "completed",
            "completed_at": created_at + 1,
            "error": None,
            "incomplete_details": None,
            "instructions": body.get("instructions"),
            "max_output_tokens": body.get("max_output_tokens"),
            "model": model,
            "output": [
                {
                    "id": msg_id,
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {
                            "type": "output_text",
                            "text": content,
                            "annotations": [],
                        }
                    ],
                }
            ],
            "output_text": content,
            "parallel_tool_calls": True,
            "previous_response_id": None,
            "reasoning": {"effort": None, "summary": None},
            "store": False,
            "temperature": body.get("temperature", 1),
            "text": {"format": {"type": "text"}},
            "tool_choice": "auto",
            "tools": [],
            "top_p": body.get("top_p", 1),
            "truncation": "disabled",
            "usage": {
                "input_tokens": 100,
                "input_tokens_details": {"cached_tokens": 0},
                "output_tokens": 50,
                "output_tokens_details": {"reasoning_tokens": 0},
                "total_tokens": 150,
            },
            "user": None,
            "metadata": {},
        }

        if stream:
            # SSE ストリーミング応答（Responses API 形式）
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()

            seq = 1

            def sse(data: dict) -> bytes:
                line = f"data: {json.dumps(data)}\n\n"
                return line.encode("utf-8")

            events = [
                sse({"type": "response.created", "response": {**response_base, "status": "in_progress", "completed_at": None, "output": []}, "sequence_number": seq}),
                sse({"type": "response.in_progress", "response": {**response_base, "status": "in_progress", "completed_at": None, "output": []}, "sequence_number": seq + 1}),
                sse({"type": "response.output_item.added", "output_index": 0, "item": {"id": msg_id, "type": "message", "role": "assistant", "status": "in_progress", "content": []}, "sequence_number": seq + 2}),
                sse({"type": "response.content_part.added", "item_id": msg_id, "output_index": 0, "content_index": 0, "part": {"type": "output_text", "text": "", "annotations": []}, "sequence_number": seq + 3}),
                sse({"type": "response.output_text.delta", "item_id": msg_id, "output_index": 0, "content_index": 0, "delta": content, "sequence_number": seq + 4}),
                sse({"type": "response.output_text.done", "item_id": msg_id, "output_index": 0, "content_index": 0, "text": content, "sequence_number": seq + 5}),
                sse({"type": "response.content_part.done", "item_id": msg_id, "output_index": 0, "content_index": 0, "part": {"type": "output_text", "text": content, "annotations": []}, "sequence_number": seq + 6}),
                sse({"type": "response.output_item.done", "output_index": 0, "item": {"id": msg_id, "type": "message", "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": content, "annotations": []}]}, "sequence_number": seq + 7}),
                sse({"type": "response.completed", "response": response_base, "sequence_number": seq + 8}),
            ]
            for chunk in events:
                self.wfile.write(chunk)
                self.wfile.flush()
                if event_delay > 0:
                    time.sleep(event_delay)
        else:
            self._send_json(200, response_base)

    def do_POST(self) -> None:
        """POST リクエストをルーティングする"""
        if self.path in ("/v1/chat/completions", "/chat/completions"):
            self._handle_chat_completions()
        elif self.path.startswith("/v1/messages"):
            self._handle_messages()
        elif self.path in ("/responses", "/v1/responses"):
            # OpenAI Responses API エンドポイント（opencode が使用）
            self._handle_responses()
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
