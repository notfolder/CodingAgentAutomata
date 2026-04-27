"""
LLM キー検証とモデル候補取得サービスモジュール。

LiteLLM エンドポイントに接続して Virtual Key の有効性を検証し、
利用可能なモデル一覧を取得する。
"""

import logging
import os
from typing import Optional

import httpx

# ロガーを設定
logger = logging.getLogger(__name__)

# LiteLLM エンドポイントのデフォルト URL
_DEFAULT_LITELLM_ENDPOINT = "http://litellm:4000"


class ModelCandidateService:
    """
    LiteLLM エンドポイントへのキー検証とモデル候補取得を行うサービスクラス。

    LiteLLM プロキシの /models エンドポイントを使用して
    Virtual Key の有効性確認と利用可能モデルの一覧取得を行う。
    """

    def __init__(
        self,
        endpoint: Optional[str] = None,
        timeout_sec: float = 10.0,
    ) -> None:
        """
        ModelCandidateService を初期化する。

        Args:
            endpoint: LiteLLM エンドポイント URL
                      省略時は環境変数 LITELLM_ENDPOINT またはデフォルト値を使用する
            timeout_sec: HTTP リクエストのタイムアウト秒数（デフォルト: 10.0秒）
        """
        # エンドポイントは引数 → LITELLM_ENDPOINT 環境変数 → LITELLM_PROXY_URL 環境変数 → デフォルト値 の優先順で決定する
        self._endpoint: str = (
            endpoint
            or os.environ.get("LITELLM_ENDPOINT")
            or os.environ.get("LITELLM_PROXY_URL", _DEFAULT_LITELLM_ENDPOINT)
        ).rstrip("/")
        self._timeout_sec = timeout_sec
        logger.debug(
            "ModelCandidateService: 初期化完了 endpoint=%s, timeout=%.1f秒",
            self._endpoint,
            timeout_sec,
        )

    async def validate_key(self, key: str) -> tuple[bool, str]:
        """
        LiteLLM エンドポイントの /models に GET リクエストを送信して
        Virtual Key の有効性を検証する。

        Authorization ヘッダーに Bearer トークンとして key を設定する。
        200 が返れば有効、エラーが返れば無効と判定する。

        Args:
            key: 検証対象の Virtual Key（LiteLLM キー）

        Returns:
            tuple[bool, str]: (有効かどうか, エラーメッセージ)
                              有効の場合は (True, "")
                              無効の場合は (False, エラーメッセージ)
                              エンドポイントに接続できない場合は (True, "") を返す（スキップ）
        """
        url = f"{self._endpoint}/models"
        logger.debug("ModelCandidateService.validate_key: GET %s", url)

        try:
            async with httpx.AsyncClient(timeout=self._timeout_sec) as client:
                response = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {key}"},
                )
            if response.status_code == 200:
                logger.debug("ModelCandidateService.validate_key: キー検証成功")
                return True, ""
            else:
                error_msg = (
                    f"LiteLLM エンドポイントが {response.status_code} を返しました"
                )
                logger.warning(
                    "ModelCandidateService.validate_key: キー検証失敗 status=%d",
                    response.status_code,
                )
                return False, error_msg
        except httpx.TimeoutException as exc:
            # タイムアウト時はエンドポイントに接続できないとみなしてスキップする
            logger.warning(
                "ModelCandidateService.validate_key: タイムアウトのためキー検証をスキップします: %s", exc
            )
            return True, ""
        except (httpx.ConnectError, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
            # エンドポイントに接続できない場合（LiteLLMが未起動など）はスキップする
            logger.warning(
                "ModelCandidateService.validate_key: LiteLLM エンドポイントに接続できないためキー検証をスキップします: %s", exc
            )
            return True, ""
        except Exception as exc:
            # その他の予期しないエラーもスキップとして扱う
            logger.warning(
                "ModelCandidateService.validate_key: 接続エラーのためキー検証をスキップします: %s", exc
            )
            return True, ""

    async def fetch_models(self, key: str) -> list[str]:
        """
        LiteLLM の /models エンドポイントから利用可能なモデル一覧を取得する。

        取得に失敗した場合は空リストを返す（WARNING ログを記録）。

        Args:
            key: 認証に使用する Virtual Key

        Returns:
            list[str]: モデル ID の文字列リスト。取得失敗時は空リスト
        """
        url = f"{self._endpoint}/models"
        logger.debug("ModelCandidateService.fetch_models: GET %s", url)

        try:
            async with httpx.AsyncClient(timeout=self._timeout_sec) as client:
                response = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {key}"},
                )
            if response.status_code != 200:
                logger.warning(
                    "ModelCandidateService.fetch_models: "
                    "モデル一覧取得失敗 status=%d",
                    response.status_code,
                )
                return []

            # OpenAI 互換の /models レスポンスを解析する
            # レスポンス形式: {"data": [{"id": "model-name", ...}, ...]}
            data: dict = response.json()
            models_data: list[dict] = data.get("data", [])
            model_ids: list[str] = [
                m.get("id", "")
                for m in models_data
                if isinstance(m, dict) and m.get("id")
            ]
            logger.debug(
                "ModelCandidateService.fetch_models: %d モデルを取得しました",
                len(model_ids),
            )
            return model_ids

        except Exception as exc:
            logger.warning(
                "ModelCandidateService.fetch_models: モデル一覧取得中にエラーが発生しました"
                "（空リストを返します）: %s",
                exc,
            )
            return []
