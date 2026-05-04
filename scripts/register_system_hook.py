#!/usr/bin/env python3
"""
GitLab System Hook 手動登録スクリプト。

GITLAB_ADMIN_PAT 環境変数で指定した管理者用 PAT を使って GitLab に
System Hook を冪等登録する。同一 URL・同一イベント設定が既に存在する場合は
再利用し、存在しない場合のみ新規登録する。

使い方:
    GITLAB_ADMIN_PAT=<PAT> python scripts/register_system_hook.py

必須環境変数:
    GITLAB_ADMIN_PAT      管理者用 Personal Access Token
    GITLAB_API_URL        GitLab の URL（デフォルト: http://localhost:8929）
    GITLAB_WEBHOOK_SECRET Webhook シークレット（デフォルト: test-webhook-secret）

任意環境変数:
    WEBHOOK_URL           本システム Webhook サーバーの URL
                          （デフォルト: http://localhost:8080/webhook）

終了コード:
    0: System Hook の登録または再利用に成功した場合
    1: GITLAB_ADMIN_PAT 未設定または API 呼び出し失敗
"""

import os
import sys

import requests

# -----------------------------------------------------------------------
# デフォルト設定値
# -----------------------------------------------------------------------

_DEFAULT_API_URL = "http://localhost:8929"
_DEFAULT_WEBHOOK_URL = "http://localhost:8080/webhook"
_DEFAULT_WEBHOOK_SECRET = "test-webhook-secret"


def _gitlab_api(
    method: str,
    path: str,
    token: str,
    api_url: str,
    **kwargs,
) -> requests.Response:
    """GitLab API 呼び出しのラッパー。

    Args:
        method: HTTP メソッド（"GET"・"POST" など）
        path: GitLab API のパス（例: "/hooks"）
        token: PRIVATE-TOKEN ヘッダーに付与する管理者用 PAT
        api_url: GitLab のベース URL
        **kwargs: requests.request に渡す追加引数

    Returns:
        requests.Response オブジェクト

    Raises:
        requests.RequestException: 通信エラー発生時
    """
    url = f"{api_url}/api/v4{path}"
    headers = {"PRIVATE-TOKEN": token, "Content-Type": "application/json"}
    return requests.request(method, url, headers=headers, timeout=30, **kwargs)


def _register_system_hook(
    admin_pat: str,
    api_url: str,
    webhook_url: str,
    secret: str,
) -> None:
    """System Hook を照合して冪等登録するコア処理。

    GitLab 管理 API GET /api/v4/hooks で既存の System Hook 一覧を取得し、
    url・issues_events・merge_requests_events が全て一致する設定が存在しない
    場合のみ POST /api/v4/hooks で新規登録する。

    登録済みの場合は再利用メッセージを出力して正常終了する。
    登録失敗の場合は失敗内容を標準エラーに出力して sys.exit(1) で終了する。

    Args:
        admin_pat: GitLab 管理者用 Personal Access Token
        api_url: GitLab のベース URL
        webhook_url: System Hook の送信先 URL
        secret: System Hook の Secret Token
    """
    # 既存 System Hook 一覧を取得する
    try:
        list_resp = _gitlab_api("GET", "/hooks", admin_pat, api_url)
    except requests.RequestException as exc:
        print(f"エラー: GitLab API への接続に失敗しました: {exc}", file=sys.stderr)
        sys.exit(1)

    if list_resp.status_code != 200:
        print(
            f"エラー: System Hook 一覧取得失敗 (HTTP {list_resp.status_code}): "
            f"{list_resp.text[:200]}",
            file=sys.stderr,
        )
        sys.exit(1)

    existing_hooks = list_resp.json() if isinstance(list_resp.json(), list) else []

    # url・issues_events・merge_requests_events の三条件で照合する
    target_hook = next(
        (
            h for h in existing_hooks
            if h.get("url") == webhook_url
            and h.get("issues_events") is True
            and h.get("merge_requests_events") is True
        ),
        None,
    )

    if target_hook:
        print(
            f"System Hook を再利用します（既存設定）: {webhook_url} "
            f"(id={target_hook.get('id')})"
        )
        return

    # 一致する設定が存在しない場合は新規登録する
    payload = {
        "url": webhook_url,
        "token": secret,
        "issues_events": True,
        "merge_requests_events": True,
        "push_events": False,
        "enable_ssl_verification": False,
    }
    try:
        resp = _gitlab_api("POST", "/hooks", admin_pat, api_url, json=payload)
    except requests.RequestException as exc:
        print(f"エラー: GitLab API への接続に失敗しました: {exc}", file=sys.stderr)
        sys.exit(1)

    if resp.status_code == 201:
        print(f"System Hook を登録しました: {webhook_url}")
    else:
        print(
            f"エラー: System Hook 登録失敗 (HTTP {resp.status_code}): "
            f"{resp.text[:200]}",
            file=sys.stderr,
        )
        sys.exit(1)


def main() -> None:
    """手動登録コマンドのエントリーポイント。

    環境変数を検証し、_register_system_hook() を呼び出して System Hook を登録する。
    GITLAB_ADMIN_PAT が未設定の場合は標準エラーにメッセージを出力して終了コード 1 で終了する。
    """
    # 管理者用 PAT を確認する
    admin_pat = os.environ.get("GITLAB_ADMIN_PAT", "")
    if not admin_pat:
        print(
            "エラー: GITLAB_ADMIN_PAT が設定されていません。\n"
            "環境変数に管理者用 Personal Access Token を設定してください。\n"
            "例: GITLAB_ADMIN_PAT=glpat-xxxx python scripts/register_system_hook.py",
            file=sys.stderr,
        )
        sys.exit(1)

    # その他の設定を環境変数から読み込む
    api_url = os.environ.get("GITLAB_API_URL", _DEFAULT_API_URL)
    webhook_url = os.environ.get("WEBHOOK_URL", _DEFAULT_WEBHOOK_URL)
    secret = os.environ.get("GITLAB_WEBHOOK_SECRET", _DEFAULT_WEBHOOK_SECRET)

    # System Hook を冪等登録する
    _register_system_hook(admin_pat, api_url, webhook_url, secret)


if __name__ == "__main__":
    main()
