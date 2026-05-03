"""
Webhook 関連 Pydantic スキーマ定義モジュール。

Group Webhook 管理APIのレスポンス・リクエストスキーマを定義する。
"""

from typing import Optional

from pydantic import BaseModel


class GroupWithWebhookStatusResponse(BaseModel):
    """グループ + Webhook登録状況レスポンススキーマ。"""

    # GitLab グループID
    group_id: int
    # グループ名
    group_name: str
    # グループのフルパス
    group_path: str
    # 登録済みWebhookのID（未登録時はNone）
    webhook_id: Optional[int] = None
    # 登録済みWebhookのURL（未登録時はNone）
    webhook_url: Optional[str] = None
    # Webhook登録済みかどうか
    is_registered: bool


class WebhookCreatedResponse(BaseModel):
    """Webhook作成成功レスポンススキーマ。"""

    # 作成されたWebhookのID
    hook_id: int
    # 作成されたWebhookのURL
    url: str
