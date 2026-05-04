"""
Webhook サービスモジュール。

Group Webhookの取得・登録・削除のビジネスロジックを担当する。
GitLabClient および SystemSettingsService に依存する。
"""

import logging
import os
from typing import Optional

import gitlab.exceptions
from sqlalchemy.orm import Session

from backend.schemas.webhook import GroupWithWebhookStatusResponse, WebhookCreatedResponse
from backend.services.system_settings_service import SystemSettingsService
from shared.gitlab_client.gitlab_client import GitLabClient

logger = logging.getLogger(__name__)


def _build_gitlab_client() -> GitLabClient:
    """
    環境変数から GitLabClient を構築する。

    Returns:
        GitLabClient: 初期化済みの GitLabClient インスタンス

    Raises:
        RuntimeError: 必要な環境変数が未設定の場合
    """
    pat = os.environ.get("GITLAB_PAT", "")
    api_url_internal = os.environ.get("GITLAB_API_URL_INTERNAL", "").strip()
    api_url_external = os.environ.get("GITLAB_API_URL", "").strip()
    api_url = api_url_internal or api_url_external
    if not pat or not api_url:
        raise RuntimeError(
            "GITLAB_PAT または GITLAB_API_URL/GITLAB_API_URL_INTERNAL 環境変数が未設定です。"
        )
    return GitLabClient(pat=pat, api_url=api_url)


class WebhookService:
    """Group Webhook の取得・登録・削除ビジネスロジックを担当するサービスクラス。"""

    def __init__(self, db: Session) -> None:
        """
        初期化。

        Args:
            db: SQLAlchemy データベースセッション
        """
        self._db = db
        self._gitlab_client = _build_gitlab_client()
        self._settings_service = SystemSettingsService(db)

    def get_groups_with_status(self) -> list[GroupWithWebhookStatusResponse]:
        """
        botトークンで取得できる最上位グループ一覧と、各グループのWebhook登録状況を返す。

        Returns:
            list[GroupWithWebhookStatusResponse]: グループ + Webhook登録状況のリスト

        Raises:
            RuntimeError: GitLab API 呼び出し失敗時
        """
        try:
            groups = self._gitlab_client.get_top_level_groups()
        except Exception as exc:
            logger.error("GitLab APIからグループ一覧取得に失敗しました: %s", exc)
            raise RuntimeError(f"GitLab APIからグループ一覧を取得できませんでした: {exc}") from exc

        result: list[GroupWithWebhookStatusResponse] = []

        for group in groups:
            group_id: int = group["id"]
            group_name: str = group.get("name", "")
            group_path: str = group.get("full_path", group.get("path", ""))

            # 各グループのWebhook一覧を取得して登録状況を判定する
            try:
                hooks = self._gitlab_client.list_group_hooks(group_id)
            except Exception as exc:
                logger.warning(
                    "グループ %d のWebhook一覧取得に失敗しました（スキップ）: %s", group_id, exc
                )
                hooks = []

            if hooks:
                # 登録済みの場合は最初のWebhookのIDとURLを返す
                first_hook = hooks[0]
                result.append(
                    GroupWithWebhookStatusResponse(
                        group_id=group_id,
                        group_name=group_name,
                        group_path=group_path,
                        webhook_id=first_hook.get("id"),
                        webhook_url=first_hook.get("url"),
                        is_registered=True,
                    )
                )
            else:
                result.append(
                    GroupWithWebhookStatusResponse(
                        group_id=group_id,
                        group_name=group_name,
                        group_path=group_path,
                        webhook_id=None,
                        webhook_url=None,
                        is_registered=False,
                    )
                )

        return result

    def register_webhook(
        self,
        group_id: int,
        username: Optional[str] = None,
    ) -> WebhookCreatedResponse:
        """
        指定グループにWebhookを登録する。

        Args:
            group_id: GitLabグループID
            username: 操作ユーザー名（監査ログ用）

        Returns:
            WebhookCreatedResponse: 作成されたWebhook情報

        Raises:
            ValueError: webhook_receive_url が未設定の場合
            RuntimeError: GitLab API 呼び出し失敗時
        """
        # システム設定からWebhook受信URLを取得する
        webhook_url = self._settings_service.get_webhook_receive_url()
        if not webhook_url:
            raise ValueError(
                "Webhook受信URLが未設定です。システム設定で設定してください。"
            )

        # シークレットトークンを環境変数から取得する
        # 未設定（空文字列）の場合はシークレットなしで登録する（設定必須ではないが推奨）
        secret = os.environ.get("GITLAB_WEBHOOK_SECRET", "")

        try:
            hook = self._gitlab_client.create_group_webhook(
                group_id=group_id,
                url=webhook_url,
                secret=secret,
            )
        except Exception as exc:
            logger.error(
                "GitLab APIへのWebhook登録に失敗しました: group_id=%d, error=%s",
                group_id,
                exc,
            )
            raise RuntimeError(f"GitLab APIへのWebhook登録に失敗しました: {exc}") from exc

        if hook is None:
            raise RuntimeError("GitLab APIへのWebhook登録に失敗しました。")

        hook_id: int = hook["id"]
        hook_url: str = hook.get("url", webhook_url)

        logger.info(
            "Webhook登録完了: user=%s, group_id=%d, hook_id=%d",
            username or "unknown",
            group_id,
            hook_id,
        )

        return WebhookCreatedResponse(hook_id=hook_id, url=hook_url)

    def delete_webhook(
        self,
        group_id: int,
        hook_id: int,
        username: Optional[str] = None,
    ) -> None:
        """
        指定グループのWebhookを削除する。

        Args:
            group_id: GitLabグループID
            hook_id: 削除するWebhookのID
            username: 操作ユーザー名（監査ログ用）

        Raises:
            KeyError: 対象Webhookが存在しない場合（GitLab 404）
            RuntimeError: GitLab API 呼び出し失敗時
        """
        try:
            self._gitlab_client.delete_group_webhook(
                group_id=group_id,
                hook_id=hook_id,
            )
        except (KeyError, gitlab.exceptions.GitlabHttpError) as exc:
            # KeyError: グループが存在しない（gitlab_client内で変換）
            # GitlabHttpError(404): hookが存在しない
            is_not_found = isinstance(exc, KeyError) or (
                isinstance(exc, gitlab.exceptions.GitlabHttpError)
                and getattr(exc, "response_code", None) == 404
            )
            if is_not_found:
                logger.warning(
                    "削除対象のWebhookが存在しません: group_id=%d, hook_id=%d",
                    group_id,
                    hook_id,
                )
                raise KeyError(
                    f"対象のWebhookが見つかりません: group_id={group_id}, hook_id={hook_id}"
                ) from exc
            logger.error(
                "GitLab APIからのWebhook削除に失敗しました: group_id=%d, hook_id=%d, error=%s",
                group_id,
                hook_id,
                exc,
            )
            raise RuntimeError(f"GitLab APIからのWebhook削除に失敗しました: {exc}") from exc
        except Exception as exc:
            logger.error(
                "GitLab APIからのWebhook削除に失敗しました: group_id=%d, hook_id=%d, error=%s",
                group_id,
                hook_id,
                exc,
            )
            raise RuntimeError(f"GitLab APIからのWebhook削除に失敗しました: {exc}") from exc

        logger.info(
            "Webhook削除完了: user=%s, group_id=%d, hook_id=%d",
            username or "unknown",
            group_id,
            hook_id,
        )
