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
        last_user = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"),
            "Hello",
        )

        # F-3 テンプレート用: branch_name / mr_title を含む JSON を返す
        if "branch_name" in last_user or "MRタイトル" in last_user or "ブランチ名" in last_user:
            content = (
                'ブランチ名とMRタイトルを生成しました。\n'
                '{"branch_name": "feature/mock-implementation", '
                '"mr_title": "Draft: Mock implementation"}'
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
