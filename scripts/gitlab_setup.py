#!/usr/bin/env python3
"""
GitLab テスト環境セットアップスクリプト（E2E テスト用）

GitLab CE を docker compose --profile test で起動した後に実行する。
以下をセットアップする:
  1. GitLab 管理者パスワードのリセット（初期 root パスワード取得）
  2. bot ユーザー作成・PAT 発行
  3. テスト用プロジェクト作成
  4. Webhook 設定
  5. テストユーザー作成（GitLab）
  6. 本システムの管理者・テストユーザー登録
  7. セットアップ結果を .env.test として出力

使い方:
    docker compose --profile test up -d gitlab
    # GitLab が起動するまで待機（5〜10分）
    python scripts/gitlab_setup.py

環境変数:
    GITLAB_URL         GitLab の URL（デフォルト: http://localhost:8929）
    WEBHOOK_URL        Webhook サーバーの URL（デフォルト: http://localhost:8080/webhook）
    BACKEND_URL        Backend の URL（デフォルト: http://localhost:8000）
    ADMIN_USERNAME     本システム管理者のユーザー名（デフォルト: admin）
    ADMIN_PASSWORD     本システム管理者のパスワード（デフォルト: Admin@123456）
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

GITLAB_URL = os.environ.get("GITLAB_URL", "http://localhost:8929")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "http://localhost:8080/webhook")
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@123456")

# デフォルトモデル設定（.env の DEFAULT_CLAUDE_MODEL / DEFAULT_OPENAI_MODEL_LITELLM で変更可能）
DEFAULT_CLAUDE_MODEL = os.environ.get("DEFAULT_CLAUDE_MODEL", "claude-haiku-4-5-20251001")
DEFAULT_OPENAI_MODEL_LITELLM = os.environ.get("DEFAULT_OPENAI_MODEL_LITELLM", "openai/gpt-4o-mini")

BOT_USERNAME = "coding-agent-bot"
BOT_EMAIL = "coding-agent-bot@example.com"
BOT_PASSWORD = "Bot@SecurePassword123!"
TEST_PROJECT_NAME = "coding-agent-test"
BOT_LABEL = "coding agent"

TEST_USERS = [
    {
        "username": "testuser-opencode",
        "email": "testuser-opencode@example.com",
        "password": "Test@123456",
        "name": "Test User OpenCode",
        "default_cli": "opencode",
        "default_model": DEFAULT_OPENAI_MODEL_LITELLM,
    },
    {
        "username": "testuser-claude",
        "email": "testuser-claude@example.com",
        "password": "Test@123456",
        "name": "Test User Claude",
        "default_cli": "claude",
        "default_model": DEFAULT_CLAUDE_MODEL,
    },
]


# -----------------------------------------------------------------------
# ヘルパー関数
# -----------------------------------------------------------------------

def _gl(method: str, path: str, token: str, **kwargs) -> requests.Response:
    """GitLab API 呼び出しヘルパー"""
    url = f"{GITLAB_URL}/api/v4{path}"
    headers = {"PRIVATE-TOKEN": token, "Content-Type": "application/json"}
    return requests.request(method, url, headers=headers, timeout=30, **kwargs)


def _backend(method: str, path: str, token: str = "", **kwargs) -> requests.Response:
    """Backend API 呼び出しヘルパー"""
    url = f"{BACKEND_URL}/api{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.request(method, url, headers=headers, timeout=30, **kwargs)


def wait_for_gitlab(max_wait: int = 600) -> bool:
    """GitLab が起動するまで待機する（最大 max_wait 秒）"""
    logger.info("GitLab の起動を待機中... (最大 %d 秒)", max_wait)
    start = time.time()
    while time.time() - start < max_wait:
        try:
            resp = requests.get(f"{GITLAB_URL}/-/health", timeout=5)
            if resp.status_code == 200:
                logger.info("GitLab が起動しました")
                return True
        except Exception:
            pass
        time.sleep(10)
        elapsed = int(time.time() - start)
        if elapsed % 30 == 0:
            logger.info("  ... %d 秒経過", elapsed)
    return False


def get_root_token() -> str:
    """GitLab root ユーザーの初期トークンを取得・生成する"""
    # docker exec で初期パスワードを確認
    import subprocess
    try:
        result = subprocess.run(
            ["docker", "exec", "codingagentautomata-gitlab-1",
             "cat", "/etc/gitlab/initial_root_password"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.startswith("Password:"):
                    init_password = line.split(":", 1)[1].strip()
                    logger.info("初期 root パスワードを取得しました")
                    # root でログインして PAT を作成
                    return create_root_pat(init_password)
    except Exception as e:
        logger.warning("初期パスワード取得失敗: %s", e)

    # フォールバック: 既知のパスワードで試みる
    for pw in ["5iveL!fe", "gitlabroot", "rootpassword"]:
        token = create_root_pat(pw)
        if token:
            return token

    logger.error("root PAT の取得に失敗しました。GITLAB_ADMIN_TOKEN を手動で設定してください。")
    return ""


def create_root_pat(root_password: str) -> str:
    """root ユーザーで PAT を作成する"""
    try:
        # ログイン
        session = requests.Session()
        # CSRF トークン取得
        resp = session.get(f"{GITLAB_URL}/users/sign_in", timeout=10)
        if resp.status_code != 200:
            return ""

        # Ruby API を使って PAT 作成（管理者ランナー経由）
        import subprocess
        script = """
user = User.find_by_username('root')
token = user.personal_access_tokens.create(
  name: 'e2e-admin-token',
  scopes: [:api, :read_api, :write_repository, :sudo],
  expires_at: 1.year.from_now
)
puts token.token
"""
        result = subprocess.run(
            ["docker", "exec", "codingagentautomata-gitlab-1",
             "gitlab-rails", "runner", script],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            token = result.stdout.strip().splitlines()[-1]
            if token and len(token) > 10:
                logger.info("root PAT を作成しました: %s...", token[:10])
                return token
    except Exception as e:
        logger.warning("PAT 作成失敗: %s", e)
    return ""


def setup_gitlab_bot(root_token: str) -> tuple[str, str]:
    """
    bot ユーザーを作成して PAT を発行する

    Returns:
        (bot_user_id, bot_pat)
    """
    # bot ユーザー作成
    resp = _gl("POST", "/users", root_token, json={
        "username": BOT_USERNAME,
        "email": BOT_EMAIL,
        "password": BOT_PASSWORD,
        "name": "Coding Agent Bot",
        "skip_confirmation": True,
    })
    if resp.status_code == 201:
        bot_id = str(resp.json()["id"])
        logger.info("bot ユーザー '%s' を作成しました (ID: %s)", BOT_USERNAME, bot_id)
    elif resp.status_code == 409:
        resp2 = _gl("GET", f"/users?username={BOT_USERNAME}", root_token)
        bot_id = str(resp2.json()[0]["id"])
        logger.info("bot ユーザー '%s' は既に存在します", BOT_USERNAME)
    else:
        logger.error("bot ユーザー作成失敗: %s", resp.text)
        return "", ""

    # bot PAT 発行
    resp = _gl("POST", f"/users/{bot_id}/personal_access_tokens", root_token, json={
        "name": "coding-agent-bot-token",
        "scopes": ["api", "read_api", "write_repository"],
    })
    if resp.status_code == 201:
        bot_pat = resp.json()["token"]
        logger.info("bot PAT を発行しました")
        return bot_id, bot_pat
    else:
        logger.warning("bot PAT 発行失敗: %s", resp.text)
        return bot_id, ""


def setup_test_project(root_token: str, bot_user_id: str) -> str:
    """テスト用プロジェクトを作成して bot をメンバーに追加する"""
    resp = _gl("POST", "/projects", root_token, json={
        "name": TEST_PROJECT_NAME,
        "namespace_id": None,
        "visibility": "private",
        "initialize_with_readme": True,
    })
    if resp.status_code == 201:
        project_id = str(resp.json()["id"])
        logger.info("テスト用プロジェクト '%s' を作成しました (ID: %s)", TEST_PROJECT_NAME, project_id)
    elif resp.status_code == 400 and "taken" in resp.text:
        resp2 = _gl("GET", f"/projects?search={TEST_PROJECT_NAME}", root_token)
        projects = [p for p in resp2.json() if p["name"] == TEST_PROJECT_NAME]
        if not projects:
            logger.error("テスト用プロジェクトの取得に失敗しました")
            return ""
        project_id = str(projects[0]["id"])
        logger.info("テスト用プロジェクト '%s' は既に存在します", TEST_PROJECT_NAME)
    else:
        logger.error("テスト用プロジェクト作成失敗: %s", resp.text)
        return ""

    # bot をメンテナーとして追加
    if bot_user_id:
        resp = _gl("POST", f"/projects/{project_id}/members", root_token, json={
            "user_id": int(bot_user_id),
            "access_level": 40,  # Maintainer
        })
        if resp.status_code in (201, 409):
            logger.info("bot をプロジェクトメンバーに追加しました")

    # テストユーザーをプロジェクトに追加
    for user in TEST_USERS:
        resp = _gl("GET", f"/users?username={user['username']}", root_token)
        if resp.status_code == 200 and resp.json():
            uid = resp.json()[0]["id"]
            _gl("POST", f"/projects/{project_id}/members", root_token, json={
                "user_id": uid,
                "access_level": 40,
            })

    # トリガーラベル作成
    for label_name in [BOT_LABEL, "coding agent processing", "coding agent done"]:
        _gl("POST", f"/projects/{project_id}/labels", root_token, json={
            "name": label_name,
            "color": "#6699cc",
        })
        logger.info("ラベル '%s' を作成しました", label_name)

    return project_id


def setup_webhook(root_token: str, project_id: str, webhook_secret: str) -> None:
    """Webhook を設定する"""
    resp = _gl("POST", f"/projects/{project_id}/hooks", root_token, json={
        "url": WEBHOOK_URL,
        "token": webhook_secret,
        "issues_events": True,
        "merge_requests_events": True,
        "push_events": False,
        "enable_ssl_verification": False,
    })
    if resp.status_code == 201:
        logger.info("Webhook を設定しました: %s", WEBHOOK_URL)
    else:
        logger.warning("Webhook 設定失敗: %s", resp.text)


def setup_gitlab_test_users(root_token: str) -> None:
    """テスト用 GitLab ユーザーを作成する"""
    for user in TEST_USERS:
        resp = _gl("POST", "/users", root_token, json={
            "username": user["username"],
            "email": user["email"],
            "password": user["password"],
            "name": user["name"],
            "skip_confirmation": True,
        })
        if resp.status_code == 201:
            logger.info("テストユーザー '%s' を GitLab に作成しました", user["username"])
        elif resp.status_code == 409:
            logger.info("テストユーザー '%s' は GitLab に既に存在します", user["username"])
        else:
            logger.warning("テストユーザー '%s' 作成失敗: %s", user["username"], resp.text)


def setup_backend(bot_pat: str, project_id: str) -> None:
    """Backend に管理者・テストユーザーを登録する"""
    # 管理者ログイン
    resp = _backend("POST", "/auth/login", json={
        "username": ADMIN_USERNAME,
        "password": ADMIN_PASSWORD,
    })
    if resp.status_code != 200:
        logger.error("Backend ログイン失敗: %s", resp.text)
        return
    admin_token = resp.json()["access_token"]
    logger.info("Backend に管理者としてログインしました")

    # テストユーザー登録
    for user in TEST_USERS:
        # Virtual Key を mock LLM から取得
        mock_vk = f"sk-mock-{user['username']}-key"

        resp = _backend("POST", "/users", admin_token, json={
            "username": user["username"],
            "email": user["email"],
            "password": user["password"],
            "virtual_key": mock_vk,
            "default_cli": user["default_cli"],
            "default_model": user["default_model"],
            "role": "user",
        })
        if resp.status_code in (200, 201):
            logger.info("テストユーザー '%s' を Backend に登録しました", user["username"])
        elif resp.status_code == 409:
            logger.info("テストユーザー '%s' は Backend に既に存在します", user["username"])
        else:
            logger.warning("テストユーザー '%s' Backend 登録失敗: %s", user["username"], resp.text)


def save_env_test(
    root_token: str,
    bot_pat: str,
    project_id: str,
    webhook_secret: str,
) -> None:
    """テスト用環境変数を .env.test ファイルに保存する"""
    content = f"""# GitLab 統合テスト用環境変数（scripts/gitlab_setup.py が自動生成）
GITLAB_API_URL={GITLAB_URL}
GITLAB_ADMIN_TOKEN={root_token}
GITLAB_BOT_TOKEN={bot_pat}
GITLAB_BOT_NAME={BOT_USERNAME}
GITLAB_BOT_LABEL={BOT_LABEL}
GITLAB_PROJECT_ID={project_id}
GITLAB_WEBHOOK_SECRET={webhook_secret}
BACKEND_URL={BACKEND_URL}
ADMIN_USERNAME={ADMIN_USERNAME}
ADMIN_PASSWORD={ADMIN_PASSWORD}
TEST_USER_PASSWORD=Test@123456
"""
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env.test")
    with open(env_path, "w") as f:
        f.write(content)
    logger.info(".env.test を作成しました: %s", env_path)


def main() -> None:
    """メイン処理"""
    # GitLab 起動待ち
    if not wait_for_gitlab():
        logger.error("GitLab の起動タイムアウト")
        sys.exit(1)

    # root トークン取得
    root_token = os.environ.get("GITLAB_ADMIN_TOKEN", "")
    if not root_token:
        root_token = get_root_token()
    if not root_token:
        logger.error("GitLab root トークンの取得に失敗しました")
        sys.exit(1)

    # bot セットアップ
    bot_user_id, bot_pat = setup_gitlab_bot(root_token)
    if not bot_pat:
        logger.error("bot PAT の取得に失敗しました")
        sys.exit(1)

    # テスト用プロジェクト
    project_id = setup_test_project(root_token, bot_user_id)
    if not project_id:
        logger.error("テスト用プロジェクトの作成に失敗しました")
        sys.exit(1)

    # Webhook 設定
    webhook_secret = os.environ.get("GITLAB_WEBHOOK_SECRET", "test-webhook-secret")
    setup_webhook(root_token, project_id, webhook_secret)

    # GitLab テストユーザー
    setup_gitlab_test_users(root_token)

    # Backend ユーザー登録
    setup_backend(bot_pat, project_id)

    # .env.test 出力
    save_env_test(root_token, bot_pat, project_id, webhook_secret)

    logger.info("=" * 60)
    logger.info("GitLab テスト環境セットアップ完了！")
    logger.info("GITLAB_API_URL=%s", GITLAB_URL)
    logger.info("GITLAB_PROJECT_ID=%s", project_id)
    logger.info("BOT_USERNAME=%s", BOT_USERNAME)
    logger.info("=" * 60)
    logger.info("E2E テスト実行コマンド:")
    logger.info(
        "  cd e2e && npm install && "
        "BASE_URL=http://localhost:80 "
        "GITLAB_API_URL=%s "
        "GITLAB_ADMIN_TOKEN=%s... "
        "GITLAB_PROJECT_ID=%s "
        "npx playwright test tests/gitlab_integration.spec.ts",
        GITLAB_URL, root_token[:10], project_id
    )


if __name__ == "__main__":
    main()
