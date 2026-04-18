#!/usr/bin/env python3
"""
テスト環境セットアップスクリプト

- GitLab API経由でbotアカウント作成・PAT発行・Webhook設定
- テスト用プロジェクト・ユーザー作成
- LiteLLM Proxy APIでテスト用Virtual Key発行・モデル設定登録

必要な環境変数:
    GITLAB_API_URL        GitLab APIのベースURL（例: http://localhost:8929）
    GITLAB_ADMIN_TOKEN    GitLab管理者PAT
    LITELLM_PROXY_URL     LiteLLM ProxyのURL（例: http://localhost:4000）
    LITELLM_MASTER_KEY    LiteLLM Proxyのマスターキー
    WEBHOOK_URL           本システムWebhookサーバーのURL
    BACKEND_URL           本システムBackend APIのURL（例: http://localhost:8000）
    ADMIN_USERNAME        本システム管理者ユーザー名
    ADMIN_PASSWORD        本システム管理者パスワード
"""

import json
import logging
import os
import sys
import time

import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# 設定
# -----------------------------------------------------------------------

GITLAB_API_URL = os.environ.get("GITLAB_API_URL", "http://gitlab:80")
GITLAB_ADMIN_TOKEN = os.environ.get("GITLAB_ADMIN_TOKEN", "")
LITELLM_PROXY_URL = os.environ.get("LITELLM_PROXY_URL", "http://litellm:4000")
LITELLM_MASTER_KEY = os.environ.get("LITELLM_MASTER_KEY", "")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "http://producer:8080/webhook")
BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:8000")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@123456")

# テスト用アカウント定義
BOT_USERNAME = "coding-agent-bot"
BOT_EMAIL = "coding-agent-bot@example.com"
BOT_PASSWORD = "Bot@123456"

TEST_USERS = [
    {
        "username": "testuser-claude",
        "email": "testuser-claude@example.com",
        "password": "Test@123456",
        "default_cli": "claude",
        "default_model": "claude-opus-4-5",
    },
    {
        "username": "testuser-opencode",
        "email": "testuser-opencode@example.com",
        "password": "Test@123456",
        "default_cli": "opencode",
        "default_model": "openai/gpt-4o",
    },
]

TEST_PROJECT_NAME = "coding-agent-test"


def _gitlab_api(method: str, path: str, token: str, **kwargs):
    """GitLab API呼び出しのラッパー"""
    url = f"{GITLAB_API_URL}/api/v4{path}"
    headers = {"PRIVATE-TOKEN": token, "Content-Type": "application/json"}
    resp = requests.request(method, url, headers=headers, timeout=30, **kwargs)
    return resp


def _litellm_api(method: str, path: str, **kwargs):
    """LiteLLM Proxy API呼び出しのラッパー"""
    url = f"{LITELLM_PROXY_URL}{path}"
    headers = {"Authorization": f"Bearer {LITELLM_MASTER_KEY}", "Content-Type": "application/json"}
    resp = requests.request(method, url, headers=headers, timeout=30, **kwargs)
    return resp


def _backend_api(method: str, path: str, token: str = "", **kwargs):
    """Backend API呼び出しのラッパー"""
    url = f"{BACKEND_URL}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = requests.request(method, url, headers=headers, timeout=30, **kwargs)
    return resp


def setup_gitlab() -> tuple[str, str]:
    """GitLab セットアップ: botアカウント・PAT・プロジェクト・Webhookを設定する
    
    Returns:
        (bot_pat, test_project_id)
    """
    if not GITLAB_ADMIN_TOKEN:
        logger.warning("GITLAB_ADMIN_TOKEN が未設定のため GitLab セットアップをスキップします")
        return "", ""

    # botアカウント作成
    resp = _gitlab_api(
        "POST", "/users", GITLAB_ADMIN_TOKEN,
        json={
            "username": BOT_USERNAME,
            "email": BOT_EMAIL,
            "password": BOT_PASSWORD,
            "name": "Coding Agent Bot",
            "skip_confirmation": True,
        },
    )
    if resp.status_code == 201:
        bot_user_id = resp.json()["id"]
        logger.info("botアカウント '%s' を作成しました (ID: %s)", BOT_USERNAME, bot_user_id)
    elif resp.status_code == 409:
        # 既存ユーザー
        resp2 = _gitlab_api("GET", f"/users?username={BOT_USERNAME}", GITLAB_ADMIN_TOKEN)
        bot_user_id = resp2.json()[0]["id"]
        logger.info("botアカウント '%s' は既に存在します", BOT_USERNAME)
    else:
        logger.error("botアカウント作成失敗: %s", resp.text)
        return "", ""

    # bot PAT発行
    resp = _gitlab_api(
        "POST", f"/users/{bot_user_id}/personal_access_tokens", GITLAB_ADMIN_TOKEN,
        json={"name": "coding-agent-bot-token", "scopes": ["api", "read_api", "write_repository"]},
    )
    if resp.status_code == 201:
        bot_pat = resp.json()["token"]
        logger.info("bot PAT を発行しました")
    else:
        logger.warning("bot PAT 発行失敗（既存の場合は手動設定が必要）: %s", resp.text)
        bot_pat = ""

    # テスト用プロジェクト作成
    resp = _gitlab_api(
        "POST", "/projects", GITLAB_ADMIN_TOKEN,
        json={"name": TEST_PROJECT_NAME, "visibility": "private", "initialize_with_readme": True},
    )
    if resp.status_code == 201:
        test_project_id = str(resp.json()["id"])
        logger.info("テスト用プロジェクト '%s' を作成しました", TEST_PROJECT_NAME)
    elif resp.status_code == 400 and "taken" in resp.text:
        resp2 = _gitlab_api("GET", f"/projects?search={TEST_PROJECT_NAME}", GITLAB_ADMIN_TOKEN)
        test_project_id = str(resp2.json()[0]["id"])
        logger.info("テスト用プロジェクト '%s' は既に存在します", TEST_PROJECT_NAME)
    else:
        logger.error("テスト用プロジェクト作成失敗: %s", resp.text)
        return bot_pat, ""

    # Webhook設定
    resp = _gitlab_api(
        "POST", f"/projects/{test_project_id}/hooks", GITLAB_ADMIN_TOKEN,
        json={
            "url": WEBHOOK_URL,
            "issues_events": True,
            "merge_requests_events": True,
            "push_events": False,
        },
    )
    if resp.status_code == 201:
        logger.info("Webhook を設定しました: %s", WEBHOOK_URL)
    else:
        logger.warning("Webhook 設定失敗: %s", resp.text)

    # テストユーザー作成
    for user in TEST_USERS:
        resp = _gitlab_api(
            "POST", "/users", GITLAB_ADMIN_TOKEN,
            json={
                "username": user["username"],
                "email": user["email"],
                "password": user["password"],
                "name": user["username"],
                "skip_confirmation": True,
            },
        )
        if resp.status_code == 201:
            logger.info("テストユーザー '%s' を作成しました", user["username"])
        else:
            logger.info("テストユーザー '%s' は既に存在します", user["username"])

    return bot_pat, test_project_id


def setup_litellm() -> dict[str, str]:
    """LiteLLM Proxy: テスト用Virtual Keyを発行する
    
    Returns:
        {username: virtual_key} の辞書
    """
    if not LITELLM_MASTER_KEY:
        logger.warning("LITELLM_MASTER_KEY が未設定のため LiteLLM セットアップをスキップします")
        return {}

    virtual_keys: dict[str, str] = {}
    for user in TEST_USERS:
        resp = _litellm_api(
            "POST", "/key/generate",
            json={"key_alias": user["username"], "models": ["claude-opus-4-5", "openai/gpt-4o"]},
        )
        if resp.status_code == 200:
            vk = resp.json().get("key", "")
            virtual_keys[user["username"]] = vk
            logger.info("Virtual Key を発行しました: %s → %s...", user["username"], vk[:10])
        else:
            logger.warning("Virtual Key 発行失敗 (%s): %s", user["username"], resp.text)

    return virtual_keys


def setup_backend_users(virtual_keys: dict[str, str]) -> None:
    """Backend APIにテストユーザーを登録する"""
    # 管理者ログイン
    resp = _backend_api(
        "POST", "/api/auth/login",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
    )
    if resp.status_code != 200:
        logger.warning("Backend 管理者ログイン失敗: %s", resp.text)
        return
    admin_token = resp.json()["access_token"]

    for user in TEST_USERS:
        vk = virtual_keys.get(user["username"], "sk-test-placeholder")
        resp = _backend_api(
            "POST", "/api/users", admin_token,
            json={
                "username": user["username"],
                "email": user["email"],
                "password": user["password"],
                "virtual_key": vk,
                "default_cli": user["default_cli"],
                "default_model": user["default_model"],
                "role": "user",
            },
        )
        if resp.status_code == 201:
            logger.info("Backendにユーザー '%s' を登録しました", user["username"])
        elif resp.status_code == 409:
            logger.info("Backendユーザー '%s' は既に登録済みです", user["username"])
        else:
            logger.warning("Backendユーザー登録失敗 (%s): %s", user["username"], resp.text)


def main() -> None:
    """テスト環境セットアップのメイン処理"""
    logger.info("テスト環境セットアップを開始します...")

    # GitLab セットアップ
    bot_pat, test_project_id = setup_gitlab()

    # LiteLLM セットアップ
    virtual_keys = setup_litellm()

    # Backend ユーザー登録
    setup_backend_users(virtual_keys)

    logger.info("テスト環境セットアップが完了しました")
    if bot_pat:
        logger.info("bot PAT: %s (GITLAB_PAT 環境変数に設定してください)", bot_pat)
    if test_project_id:
        logger.info("テストプロジェクトID: %s (GITLAB_PROJECT_IDS 環境変数に設定してください)", test_project_id)


if __name__ == "__main__":
    main()
