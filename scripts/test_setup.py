#!/usr/bin/env python3
"""
テスト環境セットアップスクリプト

docker compose --profile test で起動した GitLab CE を含む全環境のセットアップを行う。

実行内容:
  1. GitLab CE の起動待ち（--profile test 起動時）
  2. GitLab root PAT の自動取得（GITLAB_ADMIN_TOKEN 未設定の場合は docker exec 経由で取得）
  3. bot ユーザー作成・PAT 発行
  4. テスト用プロジェクト作成・メンバー追加・ラベル設定
  5. Webhook 設定
  6. テストユーザー作成（GitLab）
  7. LiteLLM Proxy でテスト用 Virtual Key 発行（LITELLM_MASTER_KEY 設定時のみ）
  8. mock LLM で Virtual Key 発行（LITELLM_MASTER_KEY 未設定時のフォールバック）
  9. Backend にシステム管理者・テストユーザーを登録
  10. セットアップ結果を .env.test として出力

使い方:
    # GitLab CE 込みのフルセットアップ（GITLAB_ADMIN_TOKEN 不要）
    docker compose --profile test up -d
    python scripts/test_setup.py

    # 既存 GitLab を使う場合（GITLAB_ADMIN_TOKEN を事前設定）
    GITLAB_ADMIN_TOKEN=glpat-xxxx python scripts/test_setup.py

環境変数:
    GITLAB_API_URL        GitLab の URL（デフォルト: http://localhost:8929）
    GITLAB_ADMIN_TOKEN    GitLab 管理者 PAT（未設定の場合は docker exec で自動取得）
    GITLAB_CONTAINER      GitLab CE コンテナ名（デフォルト: codingagentautomata-gitlab-1）
    GITLAB_WEBHOOK_SECRET Webhook シークレット（デフォルト: test-webhook-secret）
    LITELLM_PROXY_URL     LiteLLM Proxy の URL（デフォルト: http://localhost:4000）
    LITELLM_MASTER_KEY    LiteLLM Proxy のマスターキー（未設定の場合はモック LLM を使用）
    WEBHOOK_URL           本システム Webhook サーバーの URL
    BACKEND_URL           本システム Backend の URL（デフォルト: http://localhost:8000）
    ADMIN_USERNAME        本システム管理者ユーザー名（デフォルト: admin）
    ADMIN_PASSWORD        本システム管理者パスワード（デフォルト: Admin@123456）
    WAIT_GITLAB           GitLab 起動を待機するか（デフォルト: true）
"""

import json
import logging
import os
import subprocess
import sys
import time

import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# 設定
# -----------------------------------------------------------------------

GITLAB_API_URL = os.environ.get("GITLAB_API_URL", "http://localhost:8929")
GITLAB_ADMIN_TOKEN = os.environ.get("GITLAB_ADMIN_TOKEN", "")
GITLAB_CONTAINER = os.environ.get("GITLAB_CONTAINER", "codingagentautomata-gitlab-1")
GITLAB_WEBHOOK_SECRET = os.environ.get("GITLAB_WEBHOOK_SECRET", "test-webhook-secret")
LITELLM_PROXY_URL = os.environ.get("LITELLM_PROXY_URL", "http://localhost:4000")
LITELLM_MASTER_KEY = os.environ.get("LITELLM_MASTER_KEY", "")
MOCK_LLM_URL = os.environ.get("MOCK_LLM_URL", "http://localhost:4000")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "http://localhost:8080/webhook")
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@123456")
WAIT_GITLAB = os.environ.get("WAIT_GITLAB", "true").lower() != "false"

# テスト用アカウント定義
BOT_USERNAME = "coding-agent-bot"
BOT_EMAIL = "coding-agent-bot@example.com"
BOT_PASSWORD = "Bot@SecurePassword123!"
BOT_LABEL = "coding agent"
TEST_PROJECT_NAME = "coding-agent-test"

TEST_USERS = [
    {
        "username": "testuser-claude",
        "email": "testuser-claude@example.com",
        "password": "Test@123456",
        "name": "Test User Claude",
        "default_cli": "claude",
        "default_model": "claude-opus-4-5",
    },
    {
        "username": "testuser-opencode",
        "email": "testuser-opencode@example.com",
        "password": "Test@123456",
        "name": "Test User OpenCode",
        "default_cli": "opencode",
        "default_model": "openai/gpt-4o",
    },
]


# -----------------------------------------------------------------------
# API ヘルパー関数
# -----------------------------------------------------------------------

def _gitlab_api(method: str, path: str, token: str, **kwargs) -> requests.Response:
    """GitLab API 呼び出しのラッパー"""
    url = f"{GITLAB_API_URL}/api/v4{path}"
    headers = {"PRIVATE-TOKEN": token, "Content-Type": "application/json"}
    return requests.request(method, url, headers=headers, timeout=30, **kwargs)


def _litellm_api(method: str, path: str, base_url: str, master_key: str, **kwargs) -> requests.Response:
    """LiteLLM / モック LLM API 呼び出しのラッパー"""
    url = f"{base_url}{path}"
    headers = {"Authorization": f"Bearer {master_key}", "Content-Type": "application/json"}
    return requests.request(method, url, headers=headers, timeout=30, **kwargs)


def _backend_api(method: str, path: str, token: str = "", **kwargs) -> requests.Response:
    """Backend API 呼び出しのラッパー"""
    url = f"{BACKEND_URL}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.request(method, url, headers=headers, timeout=30, **kwargs)


# -----------------------------------------------------------------------
# GitLab CE セットアップ
# -----------------------------------------------------------------------

def wait_for_gitlab(max_wait: int = 600) -> bool:
    """GitLab CE が起動して API が応答するまで待機する（最大 max_wait 秒）"""
    logger.info("GitLab CE の起動を待機中... (最大 %d 秒)", max_wait)
    start = time.time()
    while time.time() - start < max_wait:
        try:
            resp = requests.get(f"{GITLAB_API_URL}/-/health", timeout=5)
            if resp.status_code == 200:
                logger.info("GitLab CE が起動しました (%.0f 秒)", time.time() - start)
                return True
        except Exception:
            pass
        elapsed = int(time.time() - start)
        if elapsed % 60 == 0 and elapsed > 0:
            logger.info("  ... %d 秒経過", elapsed)
        time.sleep(10)
    return False


def get_root_token_via_docker() -> str:
    """GitLab CE コンテナで gitlab-rails runner を実行して root PAT を作成する"""
    ruby_script = (
        "user = User.find_by_username('root'); "
        "token = user.personal_access_tokens.build("
        "  name: 'e2e-admin-token',"
        "  scopes: ['api', 'read_api', 'write_repository', 'sudo'],"
        "  expires_at: Date.today + 365"
        "); "
        "token.save!; "
        "puts token.token"
    )
    try:
        result = subprocess.run(
            ["docker", "exec", GITLAB_CONTAINER, "gitlab-rails", "runner", ruby_script],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            token = result.stdout.strip().splitlines()[-1]
            if token and len(token) > 10:
                logger.info("docker exec 経由で root PAT を取得しました: %s...", token[:10])
                return token
        logger.warning("gitlab-rails runner エラー: %s", result.stderr[:200])
    except subprocess.TimeoutExpired:
        logger.warning("gitlab-rails runner がタイムアウトしました")
    except Exception as e:
        logger.warning("docker exec 失敗: %s", e)
    return ""


def get_or_create_root_token() -> str:
    """root PAT を取得する（環境変数 → docker exec の順で試みる）"""
    if GITLAB_ADMIN_TOKEN:
        # 環境変数が設定されていればそのまま使用
        logger.info("環境変数 GITLAB_ADMIN_TOKEN を使用します")
        return GITLAB_ADMIN_TOKEN

    logger.info("GITLAB_ADMIN_TOKEN 未設定のため docker exec 経由で PAT を取得します")
    return get_root_token_via_docker()


def setup_gitlab_bot(root_token: str) -> tuple[str, str]:
    """bot ユーザーを作成して PAT を発行する

    Returns:
        (bot_user_id, bot_pat)
    """
    # bot ユーザー作成
    resp = _gitlab_api("POST", "/users", root_token, json={
        "username": BOT_USERNAME,
        "email": BOT_EMAIL,
        "password": BOT_PASSWORD,
        "name": "Coding Agent Bot",
        "skip_confirmation": True,
    })
    if resp.status_code == 201:
        bot_id = str(resp.json()["id"])
        logger.info("bot ユーザー '%s' を作成しました (ID: %s)", BOT_USERNAME, bot_id)
    elif resp.status_code in (409, 422):
        resp2 = _gitlab_api("GET", f"/users?username={BOT_USERNAME}", root_token)
        users = resp2.json()
        if not users:
            logger.error("bot ユーザーの検索に失敗しました")
            return "", ""
        bot_id = str(users[0]["id"])
        logger.info("bot ユーザー '%s' は既に存在します", BOT_USERNAME)
    else:
        logger.error("bot ユーザー作成失敗 (%d): %s", resp.status_code, resp.text[:200])
        return "", ""

    # bot PAT 発行
    resp = _gitlab_api("POST", f"/users/{bot_id}/personal_access_tokens", root_token, json={
        "name": "coding-agent-bot-token",
        "scopes": ["api", "read_api", "write_repository"],
    })
    if resp.status_code == 201:
        bot_pat = resp.json()["token"]
        logger.info("bot PAT を発行しました")
        return bot_id, bot_pat
    else:
        logger.warning("bot PAT 発行失敗 (%d): %s", resp.status_code, resp.text[:200])
        return bot_id, ""


def setup_test_project(root_token: str, bot_user_id: str) -> str:
    """テスト用プロジェクトを作成してラベル・メンバーを設定する

    Returns:
        project_id
    """
    resp = _gitlab_api("POST", "/projects", root_token, json={
        "name": TEST_PROJECT_NAME,
        "visibility": "private",
        "initialize_with_readme": True,
    })
    if resp.status_code == 201:
        project_id = str(resp.json()["id"])
        logger.info("テスト用プロジェクト '%s' を作成しました (ID: %s)", TEST_PROJECT_NAME, project_id)
    elif resp.status_code in (400, 422) and "taken" in resp.text:
        resp2 = _gitlab_api("GET", f"/projects?search={TEST_PROJECT_NAME}&owned=true", root_token)
        projects = [p for p in resp2.json() if p["name"] == TEST_PROJECT_NAME]
        if not projects:
            # 全プロジェクトから探す
            resp2 = _gitlab_api("GET", f"/projects?search={TEST_PROJECT_NAME}", root_token)
            projects = [p for p in resp2.json() if p["name"] == TEST_PROJECT_NAME]
        if not projects:
            logger.error("テスト用プロジェクトの取得に失敗しました")
            return ""
        project_id = str(projects[0]["id"])
        logger.info("テスト用プロジェクト '%s' は既に存在します (ID: %s)", TEST_PROJECT_NAME, project_id)
    else:
        logger.error("テスト用プロジェクト作成失敗 (%d): %s", resp.status_code, resp.text[:200])
        return ""

    # bot をメンテナーとして追加
    if bot_user_id:
        _gitlab_api("POST", f"/projects/{project_id}/members", root_token, json={
            "user_id": int(bot_user_id),
            "access_level": 40,  # Maintainer
        })
        logger.info("bot をプロジェクトメンバーに追加しました")

    # テストユーザーをプロジェクトに追加
    for user in TEST_USERS:
        resp2 = _gitlab_api("GET", f"/users?username={user['username']}", root_token)
        if resp2.status_code == 200 and resp2.json():
            uid = resp2.json()[0]["id"]
            _gitlab_api("POST", f"/projects/{project_id}/members", root_token, json={
                "user_id": uid,
                "access_level": 40,
            })

    # ラベル作成
    for label_name, color in [
        (BOT_LABEL, "#6699cc"),
        ("coding agent processing", "#e67e22"),
        ("coding agent done", "#2ecc71"),
    ]:
        _gitlab_api("POST", f"/projects/{project_id}/labels", root_token, json={
            "name": label_name,
            "color": color,
        })
        logger.info("ラベル '%s' を作成しました", label_name)

    return project_id


def setup_webhook(root_token: str, project_id: str) -> None:
    """プロジェクトに Webhook を設定する"""
    resp = _gitlab_api("POST", f"/projects/{project_id}/hooks", root_token, json={
        "url": WEBHOOK_URL,
        "token": GITLAB_WEBHOOK_SECRET,
        "issues_events": True,
        "merge_requests_events": True,
        "push_events": False,
        "enable_ssl_verification": False,
    })
    if resp.status_code == 201:
        logger.info("Webhook を設定しました: %s", WEBHOOK_URL)
    else:
        logger.warning("Webhook 設定失敗 (%d): %s", resp.status_code, resp.text[:200])


def setup_gitlab_test_users(root_token: str) -> None:
    """GitLab にテストユーザーを作成する"""
    for user in TEST_USERS:
        resp = _gitlab_api("POST", "/users", root_token, json={
            "username": user["username"],
            "email": user["email"],
            "password": user["password"],
            "name": user["name"],
            "skip_confirmation": True,
        })
        if resp.status_code == 201:
            logger.info("GitLab テストユーザー '%s' を作成しました", user["username"])
        elif resp.status_code in (409, 422):
            logger.info("GitLab テストユーザー '%s' は既に存在します", user["username"])
        else:
            logger.warning("GitLab テストユーザー '%s' 作成失敗 (%d): %s",
                           user["username"], resp.status_code, resp.text[:200])


# -----------------------------------------------------------------------
# LiteLLM / モック LLM セットアップ
# -----------------------------------------------------------------------

def setup_virtual_keys() -> dict[str, str]:
    """Virtual Key を発行する

    LITELLM_MASTER_KEY が設定されていれば LiteLLM Proxy を使用し、
    そうでなければモック LLM から発行する。

    Returns:
        {username: virtual_key} の辞書
    """
    if LITELLM_MASTER_KEY:
        base_url = LITELLM_PROXY_URL
        master_key = LITELLM_MASTER_KEY
        logger.info("LiteLLM Proxy から Virtual Key を発行します")
    else:
        base_url = MOCK_LLM_URL
        master_key = "sk-master-test-key"
        logger.info("モック LLM から Virtual Key を発行します (LITELLM_MASTER_KEY 未設定)")

    virtual_keys: dict[str, str] = {}
    for user in TEST_USERS:
        try:
            resp = _litellm_api("POST", "/key/generate", base_url, master_key, json={
                "key_alias": user["username"],
                "models": ["claude-opus-4-5", "openai/gpt-4o"],
            })
            if resp.status_code == 200:
                vk = resp.json().get("key", "")
                virtual_keys[user["username"]] = vk
                logger.info("Virtual Key を発行しました: %s → %s...", user["username"], vk[:10])
            else:
                logger.warning("Virtual Key 発行失敗 (%s / %d): %s",
                               user["username"], resp.status_code, resp.text[:100])
                virtual_keys[user["username"]] = f"sk-mock-{user['username']}"
        except Exception as e:
            logger.warning("Virtual Key 発行例外 (%s): %s", user["username"], e)
            virtual_keys[user["username"]] = f"sk-mock-{user['username']}"

    return virtual_keys


# -----------------------------------------------------------------------
# Backend セットアップ
# -----------------------------------------------------------------------

def setup_backend_users(virtual_keys: dict[str, str]) -> None:
    """Backend API にテストユーザーを登録する"""
    resp = _backend_api("POST", "/api/auth/login",
                        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    if resp.status_code != 200:
        logger.warning("Backend 管理者ログイン失敗 (%d): %s", resp.status_code, resp.text[:200])
        return
    admin_token = resp.json()["access_token"]
    logger.info("Backend に管理者としてログインしました")

    for user in TEST_USERS:
        vk = virtual_keys.get(user["username"], f"sk-mock-{user['username']}")
        resp = _backend_api("POST", "/api/users", admin_token, json={
            "username": user["username"],
            "email": user["email"],
            "password": user["password"],
            "virtual_key": vk,
            "default_cli": user["default_cli"],
            "default_model": user["default_model"],
            "role": "user",
        })
        if resp.status_code in (200, 201):
            logger.info("Backend にユーザー '%s' を登録しました", user["username"])
        elif resp.status_code == 409:
            logger.info("Backend ユーザー '%s' は既に登録済みです", user["username"])
        else:
            logger.warning("Backend ユーザー登録失敗 (%s / %d): %s",
                           user["username"], resp.status_code, resp.text[:200])


# -----------------------------------------------------------------------
# .env.test 出力
# -----------------------------------------------------------------------

def save_env_test(root_token: str, bot_pat: str, project_id: str) -> None:
    """.env.test ファイルにセットアップ結果を保存する"""
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env.test")
    content = f"""# E2E テスト用環境変数（scripts/test_setup.py が自動生成）
GITLAB_API_URL={GITLAB_API_URL}
GITLAB_ADMIN_TOKEN={root_token}
GITLAB_BOT_NAME={BOT_USERNAME}
GITLAB_BOT_LABEL={BOT_LABEL}
GITLAB_PROJECT_ID={project_id}
GITLAB_WEBHOOK_SECRET={GITLAB_WEBHOOK_SECRET}
BACKEND_URL={BACKEND_URL}
BASE_URL=http://localhost:80
ADMIN_USERNAME={ADMIN_USERNAME}
ADMIN_PASSWORD={ADMIN_PASSWORD}
TEST_USER_PASSWORD=Test@123456
"""
    with open(env_path, "w") as f:
        f.write(content)
    logger.info(".env.test を保存しました: %s", env_path)


# -----------------------------------------------------------------------
# メイン処理
# -----------------------------------------------------------------------

def main() -> None:
    """テスト環境セットアップのメイン処理"""
    logger.info("=" * 60)
    logger.info("テスト環境セットアップを開始します")
    logger.info("=" * 60)

    # --- GitLab CE 起動待ち ---
    if WAIT_GITLAB:
        if not wait_for_gitlab():
            logger.error("GitLab CE の起動タイムアウト（WAIT_GITLAB=false で無効化可能）")
            sys.exit(1)

    # --- root PAT 取得 ---
    root_token = get_or_create_root_token()
    if not root_token:
        logger.warning("root PAT の取得に失敗しました。GitLab セットアップをスキップします。")
        bot_pat = ""
        project_id = ""
    else:
        # --- bot ユーザー・PAT 設定 ---
        bot_user_id, bot_pat = setup_gitlab_bot(root_token)
        if not bot_pat:
            logger.warning("bot PAT が取得できませんでした")

        # --- テスト用プロジェクト ---
        project_id = setup_test_project(root_token, bot_user_id)
        if not project_id:
            logger.warning("テスト用プロジェクトの作成に失敗しました")
        else:
            # --- Webhook 設定 ---
            setup_webhook(root_token, project_id)

        # --- GitLab テストユーザー作成 ---
        setup_gitlab_test_users(root_token)

    # --- Virtual Key 発行 ---
    virtual_keys = setup_virtual_keys()

    # --- Backend ユーザー登録 ---
    setup_backend_users(virtual_keys)

    # --- .env.test 出力 ---
    if root_token and project_id:
        save_env_test(root_token, bot_pat, project_id)

    logger.info("=" * 60)
    logger.info("テスト環境セットアップ完了！")
    if project_id:
        logger.info("GITLAB_PROJECT_ID=%s", project_id)
    logger.info("E2E テスト実行コマンド:")
    logger.info(
        "  cd e2e && npm install && "
        "BASE_URL=http://localhost:80 "
        "GITLAB_API_URL=%s "
        "GITLAB_ADMIN_TOKEN=<token> "
        "GITLAB_PROJECT_ID=%s "
        "npx playwright test",
        GITLAB_API_URL, project_id or "<未取得>",
    )
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
