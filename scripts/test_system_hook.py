#!/usr/bin/env python3
"""
System Hook 関連関数の単体テスト（UT-SH-01〜UT-SH-10）

テスト対象:
    - scripts/test_setup.py: setup_system_hook()・get_or_create_admin_pat()
    - scripts/register_system_hook.py: _register_system_hook()・main()

GitLab API 呼び出しはすべて unittest.mock でモックする。
"""

import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# scripts ディレクトリを import パスに追加する
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# テスト対象モジュールを import する
import scripts.test_setup as test_setup_module
import scripts.register_system_hook as register_module


# -----------------------------------------------------------------------
# テスト用定数
# -----------------------------------------------------------------------

_WEBHOOK_URL = "http://localhost:8080/webhook"
_WEBHOOK_SECRET = "test-webhook-secret"
_API_URL = "http://localhost:8929"
_ADMIN_PAT = "glpat-test-admin-token"


def _make_response(status_code: int, json_data=None, text: str = "") -> MagicMock:
    """モック用の requests.Response オブジェクトを生成するヘルパー。

    Args:
        status_code: HTTP ステータスコード
        json_data: json() メソッドが返すデータ
        text: text プロパティが返す文字列

    Returns:
        MagicMock で作成した Response モックオブジェクト
    """
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else []
    resp.text = text
    return resp


# -----------------------------------------------------------------------
# UT-SH-01〜UT-SH-04: setup_system_hook() のテスト
# -----------------------------------------------------------------------

class TestSetupSystemHook(unittest.TestCase):
    """scripts/test_setup.py の setup_system_hook() を対象とするテスト"""

    def setUp(self) -> None:
        """テスト前の共通設定（WEBHOOK_URL・GITLAB_WEBHOOK_SECRET をモジュール変数に設定）"""
        test_setup_module.WEBHOOK_URL = _WEBHOOK_URL
        test_setup_module.GITLAB_WEBHOOK_SECRET = _WEBHOOK_SECRET

    def test_ut_sh_01_new_registration_when_no_hooks(self) -> None:
        """UT-SH-01: GitLab API が空のリストを返す場合に POST /api/v4/hooks が呼び出されること"""
        # GET は空リストを返し、POST は 201 を返すよう設定する
        get_resp = _make_response(200, [])
        post_resp = _make_response(201, {"id": 1, "url": _WEBHOOK_URL})

        with patch.object(test_setup_module, "_gitlab_api") as mock_api:
            mock_api.side_effect = [get_resp, post_resp]
            test_setup_module.setup_system_hook(_ADMIN_PAT)

        # POST が 1 回呼び出されていることを確認する
        calls = mock_api.call_args_list
        methods = [c.args[0] for c in calls]
        self.assertIn("POST", methods, "空リストの場合は POST /api/v4/hooks が呼び出されるべき")

    def test_ut_sh_02_skip_registration_when_same_hook_exists(self) -> None:
        """UT-SH-02: 同一 URL・同一イベントの既存設定がある場合に POST が呼び出されないこと"""
        existing = [
            {
                "id": 1,
                "url": _WEBHOOK_URL,
                "issues_events": True,
                "merge_requests_events": True,
            }
        ]
        get_resp = _make_response(200, existing)

        with patch.object(test_setup_module, "_gitlab_api") as mock_api:
            mock_api.return_value = get_resp
            test_setup_module.setup_system_hook(_ADMIN_PAT)

        # POST が呼び出されていないことを確認する
        calls = mock_api.call_args_list
        methods = [c.args[0] for c in calls]
        self.assertNotIn("POST", methods, "既存設定がある場合は POST が呼び出されないべき")

    def test_ut_sh_03_warning_when_list_api_fails(self) -> None:
        """UT-SH-03: 一覧取得 API が失敗した場合に WARNING ログが出力されること"""
        error_resp = _make_response(401, text="Unauthorized")

        with patch.object(test_setup_module, "_gitlab_api") as mock_api:
            mock_api.return_value = error_resp
            with self.assertLogs(level="WARNING") as log_ctx:
                test_setup_module.setup_system_hook(_ADMIN_PAT)

        # WARNING ログが出力されていることを確認する
        self.assertTrue(
            any("WARNING" in line for line in log_ctx.output),
            "一覧取得失敗時は WARNING ログが出力されるべき",
        )

    def test_ut_sh_04_warning_when_post_returns_non_201(self) -> None:
        """UT-SH-04: 登録 API が 201 以外を返した場合に WARNING ログが出力されること"""
        get_resp = _make_response(200, [])
        post_resp = _make_response(400, text="Bad Request")

        with patch.object(test_setup_module, "_gitlab_api") as mock_api:
            mock_api.side_effect = [get_resp, post_resp]
            with self.assertLogs(level="WARNING") as log_ctx:
                test_setup_module.setup_system_hook(_ADMIN_PAT)

        # WARNING ログが出力されていることを確認する
        self.assertTrue(
            any("WARNING" in line for line in log_ctx.output),
            "POST 失敗時は WARNING ログが出力されるべき",
        )


# -----------------------------------------------------------------------
# UT-SH-05〜UT-SH-07: get_or_create_admin_pat() のテスト
# -----------------------------------------------------------------------

class TestGetOrCreateAdminPat(unittest.TestCase):
    """scripts/test_setup.py の get_or_create_admin_pat() を対象とするテスト"""

    def test_ut_sh_05_returns_env_var_when_set(self) -> None:
        """UT-SH-05: GITLAB_ADMIN_PAT が設定済みの場合にその値が返されること"""
        env = {"GITLAB_ADMIN_PAT": "glpat-from-env"}
        with patch.dict(os.environ, env, clear=False):
            result = test_setup_module.get_or_create_admin_pat()
        self.assertEqual(result, "glpat-from-env")

    def test_ut_sh_06_returns_docker_pat_when_env_not_set(self) -> None:
        """UT-SH-06: GITLAB_ADMIN_PAT 未設定かつ get_root_token_via_docker() が有効なトークンを返す場合の動作確認"""
        # GITLAB_ADMIN_PAT と GITLAB_ADMIN_TOKEN を除外した環境を用意する
        clean_env = {
            k: v for k, v in os.environ.items()
            if k not in ("GITLAB_ADMIN_PAT", "GITLAB_ADMIN_TOKEN")
        }
        docker_token = "glpat-from-docker-exec"

        with patch.dict(os.environ, clean_env, clear=True):
            with patch.object(
                test_setup_module, "get_root_token_via_docker", return_value=docker_token
            ):
                result = test_setup_module.get_or_create_admin_pat()

        self.assertEqual(result, docker_token, "docker exec で取得した PAT が返るべき")

    def test_ut_sh_07_returns_empty_when_docker_fails(self) -> None:
        """UT-SH-07: GITLAB_ADMIN_PAT 未設定かつ get_root_token_via_docker() が空文字を返す場合に空文字が返されること"""
        clean_env = {
            k: v for k, v in os.environ.items()
            if k not in ("GITLAB_ADMIN_PAT", "GITLAB_ADMIN_TOKEN")
        }

        with patch.dict(os.environ, clean_env, clear=True):
            with patch.object(
                test_setup_module, "get_root_token_via_docker", return_value=""
            ):
                result = test_setup_module.get_or_create_admin_pat()

        self.assertEqual(result, "", "docker exec 失敗時は空文字が返るべき")


# -----------------------------------------------------------------------
# UT-SH-08〜UT-SH-09: _register_system_hook() のテスト
# -----------------------------------------------------------------------

class TestRegisterSystemHook(unittest.TestCase):
    """scripts/register_system_hook.py の _register_system_hook() を対象とするテスト"""

    def test_ut_sh_08_normal_registration_flow(self) -> None:
        """UT-SH-08: 正常登録フローで _register_system_hook() が正常終了すること"""
        get_resp = _make_response(200, [])
        post_resp = _make_response(201, {"id": 1, "url": _WEBHOOK_URL})

        with patch.object(register_module, "_gitlab_api") as mock_api:
            mock_api.side_effect = [get_resp, post_resp]
            # sys.exit が呼ばれないことを確認する（例外がなければ正常終了）
            try:
                register_module._register_system_hook(
                    _ADMIN_PAT, _API_URL, _WEBHOOK_URL, _WEBHOOK_SECRET
                )
            except SystemExit:
                self.fail("正常登録フローで sys.exit() が呼ばれてはいけない")

    def test_ut_sh_09_skip_post_when_hook_exists(self) -> None:
        """UT-SH-09: 再利用判定フローで POST が呼び出されないこと"""
        existing = [
            {
                "id": 1,
                "url": _WEBHOOK_URL,
                "issues_events": True,
                "merge_requests_events": True,
            }
        ]
        get_resp = _make_response(200, existing)

        with patch.object(register_module, "_gitlab_api") as mock_api:
            mock_api.return_value = get_resp
            register_module._register_system_hook(
                _ADMIN_PAT, _API_URL, _WEBHOOK_URL, _WEBHOOK_SECRET
            )

        # POST が呼び出されていないことを確認する
        calls = mock_api.call_args_list
        methods = [c.args[0] for c in calls]
        self.assertNotIn("POST", methods, "既存設定がある場合は POST が呼び出されないべき")


# -----------------------------------------------------------------------
# UT-SH-10: main() のテスト（register_system_hook.py）
# -----------------------------------------------------------------------

class TestRegisterSystemHookMain(unittest.TestCase):
    """scripts/register_system_hook.py の main() を対象とするテスト"""

    def test_ut_sh_10_exit_1_when_admin_pat_not_set(self) -> None:
        """UT-SH-10: GITLAB_ADMIN_PAT 未設定時に sys.exit(1) が呼び出されること"""
        clean_env = {
            k: v for k, v in os.environ.items()
            if k != "GITLAB_ADMIN_PAT"
        }

        with patch.dict(os.environ, clean_env, clear=True):
            with self.assertRaises(SystemExit) as ctx:
                register_module.main()

        self.assertEqual(ctx.exception.code, 1, "GITLAB_ADMIN_PAT 未設定時は終了コード 1 であるべき")


# -----------------------------------------------------------------------
# エントリーポイント
# -----------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
