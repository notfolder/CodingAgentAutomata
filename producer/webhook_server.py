"""
GitLab Webhook 受信サーバーモジュール。

aiohttp を使用して HTTP サーバーを起動し、GitLab Webhook リクエストを受信・検証する。
GitLab の Webhook はシークレットトークンを X-Gitlab-Token ヘッダーに直接送信する仕様のため、
トークンの直接比較による検証を行う。
"""

import logging

from aiohttp import web

from shared.config.config import Settings

# ロガーを設定
logger = logging.getLogger(__name__)


class WebhookServer:
    """
    GitLab Webhook リクエストを受信・検証する HTTP サーバー。

    aiohttp を使用して非同期で動作する。
    X-Gitlab-Token ヘッダーによるシークレットトークン検証を行う。
    """

    def __init__(self, event_handler: object, settings: Settings) -> None:
        """
        WebhookServer を初期化する。

        Args:
            event_handler: イベント処理を担当する GitLabEventHandler インスタンス
            settings: アプリケーション設定インスタンス
        """
        self._event_handler = event_handler
        self._settings = settings
        # aiohttp Web アプリケーションの初期化
        self._app = web.Application()
        self._app.router.add_post("/webhook", self._handle_webhook)
        self._app.router.add_get("/health", self._handle_health)
        logger.debug("WebhookServer initialized: port=%d", settings.webhook_port)

    async def start(self) -> None:
        """
        HTTP サーバーを起動する。

        WEBHOOK_PORT（デフォルト: 8080）でリッスンし、
        Ctrl+C 等のシグナルで停止するまでリクエストを受け付け続ける。
        """
        runner = web.AppRunner(self._app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", self._settings.webhook_port)
        await site.start()
        logger.info(
            "WebhookServer started: listening on port %d",
            self._settings.webhook_port,
        )
        # サーバーを永続的に動作させるため、無限待機する
        # asyncio.gather で PollingLoop と並行動作するため、ここでは停止しない
        import asyncio
        await asyncio.Event().wait()

    async def _handle_webhook(self, request: web.Request) -> web.Response:
        """
        POST /webhook エンドポイントのハンドラー。

        1. X-Gitlab-Token ヘッダーを GITLAB_WEBHOOK_SECRET と直接比較して検証する
        2. 一致しない場合は 403 Forbidden を返す
        3. リクエストボディを JSON パースする
        4. event_handler.handle_event(payload) を呼び出してイベントを処理する
        5. 200 OK を返す

        Args:
            request: aiohttp リクエストオブジェクト

        Returns:
            HTTP レスポンス
        """
        # GitLab Webhook トークン検証
        # GitLab は X-Gitlab-Token ヘッダーにシークレットトークンをそのまま送信する
        token = request.headers.get("X-Gitlab-Token", "")
        expected = self._settings.gitlab_webhook_secret

        # X-Gitlab-Event ヘッダーを取得してログに記録する（Group Webhook 標準化）
        gitlab_event = request.headers.get("X-Gitlab-Event", "")
        logger.info(
            "WebhookServer: Webhook 受信 event=%s, remote=%s",
            gitlab_event,
            request.remote,
        )

        if expected and token != expected:
            # シークレットが設定されている場合のみ検証する
            logger.warning(
                "WebhookServer: invalid X-Gitlab-Token from %s",
                request.remote,
            )
            return web.Response(status=403, text="Forbidden: invalid token")

        # リクエストボディを JSON パース
        try:
            payload: dict = await request.json()
        except Exception as exc:
            # T-08 要件: ペイロード不正の場合は WARNING ログを記録して 200 を返す
            # （GitLab が再送しないよう 200 を返すのが一般的なプラクティス）
            logger.warning(
                "WebhookServer: JSON parse error from %s: %s",
                request.remote,
                exc,
            )
            return web.Response(status=200, text="OK")

        # イベントハンドラーに処理を委譲する
        # X-Idempotency-Key ヘッダーを渡して重複受信を抑止する
        idempotency_key = request.headers.get("X-Idempotency-Key")
        try:
            self._event_handler.handle_event(payload, idempotency_key=idempotency_key)
        except Exception as exc:
            # イベント処理エラーは 500 を返さず、ログに記録して 200 を返す
            # （GitLab が再送しないよう 200 を返すのが一般的なプラクティス）
            logger.error(
                "WebhookServer: event handler error: %s",
                exc,
                exc_info=True,
            )

        return web.Response(status=200, text="OK")

    async def _handle_health(self, request: web.Request) -> web.Response:
        """
        GET /health エンドポイントのハンドラー。

        コンテナのヘルスチェックに使用するエンドポイント。

        Args:
            request: aiohttp リクエストオブジェクト

        Returns:
            200 OK レスポンス
        """
        return web.Response(status=200, text="OK")
