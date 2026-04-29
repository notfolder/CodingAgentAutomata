#!/usr/bin/env python3
"""
システムセットアップスクリプト

初期管理者ユーザー作成・F-3/F-4初期プロンプトテンプレートDB投入・
組み込みCLIアダプタ登録を行う。

Usage:
    python scripts/setup.py [--username U --email E --password P --virtual-key K
                             --default-cli C --default-model M]
"""

import argparse
import base64
import getpass
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# SQLAlchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# cryptography
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import secrets

# bcrypt
import bcrypt

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# DB接続
# -----------------------------------------------------------------------

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://user:password@postgresql:5432/db"
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

# -----------------------------------------------------------------------
# DBモデル（shared/models/db.py と同内容をインポートまたは直接SQL使用）
# -----------------------------------------------------------------------

def _encrypt_virtual_key(plain: str, encryption_key_b64: str) -> bytes:
    """AES-256-GCM で Virtual Key を暗号化して返す（nonce先頭付加）"""
    key = base64.b64decode(encryption_key_b64)
    aesgcm = AESGCM(key)
    nonce = secrets.token_bytes(12)
    ciphertext = aesgcm.encrypt(nonce, plain.encode(), None)
    return nonce + ciphertext


def _hash_password(plain: str) -> str:
    """bcrypt（コストファクタ12）でパスワードをハッシュ化する"""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=12)).decode()


# -----------------------------------------------------------------------
# F-3 / F-4 初期プロンプトテンプレート
# -----------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_TEMPLATE_DIR = _PROJECT_ROOT / "default-template"


def _load_default_template(file_name: str) -> str:
    """default-template 配下の Markdown テンプレートを読み込む。"""
    template_path = _DEFAULT_TEMPLATE_DIR / file_name
    if not template_path.exists():
        logger.error("デフォルトテンプレートが見つかりません: %s", template_path)
        sys.exit(1)
    return template_path.read_text(encoding="utf-8")


F3_PROMPT_TEMPLATE = _load_default_template("f3_prompt_template.md")
F4_PROMPT_TEMPLATE = _load_default_template("f4_prompt_template.md")

# -----------------------------------------------------------------------
# 組み込みCLIアダプタ設定
# -----------------------------------------------------------------------

BUILTIN_ADAPTERS = [
    {
        "cli_id": "claude",
        "container_image": "coding-agent-cli-exec-claude:latest",
        # プロンプトはコンテナ内の /tmp/prompt.txt にファイルとして書き込み、
        # cat コマンドで stdin 経由で渡すことでコマンドライン引数の長さ制限を回避する。
        # claude -p に引数を渡さない場合、stdin をプロンプトとして読み取る。
        "start_command_template": (
            "cat /tmp/prompt.txt | claude -p --dangerously-skip-permissions "
            "--model {model} --mcp-config '{mcp_config}'"
        ),
        "env_mappings": json.dumps({
            "llm_api_key": "ANTHROPIC_API_KEY",
            "llm_base_url": "ANTHROPIC_BASE_URL",
        }),
        "config_content_env": None,
        "is_builtin": True,
    },
    {
        "cli_id": "opencode",
        "container_image": "coding-agent-cli-exec-opencode:latest",
        # プロンプトはコンテナ内の /tmp/prompt.txt にファイルとして書き込み、
        # cat コマンドで stdin 経由で渡す。opencode run - は stdin をプロンプトとして読み取る。
        "start_command_template": "cat /tmp/prompt.txt | opencode run - --model {model}",
        "env_mappings": json.dumps({
            "llm_api_key": "OPENAI_API_KEY",
        }),
        "config_content_env": "OPENCODE_CONFIG_CONTENT",
        "is_builtin": True,
    },
]


# -----------------------------------------------------------------------
# セットアップ処理
# -----------------------------------------------------------------------

def setup(
    username: str,
    email: str,
    password: str,
    virtual_key: str,
    default_cli: str,
    default_model: str,
) -> None:
    """セットアップ処理のメイン関数"""
    encryption_key_b64 = os.environ.get("ENCRYPTION_KEY", "")
    if not encryption_key_b64:
        logger.error("ENCRYPTION_KEY 環境変数が設定されていません")
        sys.exit(1)

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)

        # --- 組み込みCLIアダプタ登録 ---
        for adapter in BUILTIN_ADAPTERS:
            existing = db.execute(
                __import__("sqlalchemy").text(
                    "SELECT cli_id FROM cli_adapters WHERE cli_id = :cli_id"
                ),
                {"cli_id": adapter["cli_id"]},
            ).fetchone()
            if existing:
                logger.info("CLIアダプタ '%s' は既に登録済みです", adapter["cli_id"])
            else:
                db.execute(
                    __import__("sqlalchemy").text(
                        "INSERT INTO cli_adapters "
                        "(cli_id, container_image, start_command_template, "
                        "env_mappings, config_content_env, is_builtin, created_at, updated_at) "
                        "VALUES (:cli_id, :container_image, :start_command_template, "
                        ":env_mappings, :config_content_env, :is_builtin, :created_at, :updated_at)"
                    ),
                    {**adapter, "created_at": now, "updated_at": now},
                )
                logger.info("CLIアダプタ '%s' を登録しました", adapter["cli_id"])

        # --- F-3 / F-4 プロンプトテンプレート投入 ---
        for key, value in [
            ("f3_prompt_template", F3_PROMPT_TEMPLATE),
            ("f4_prompt_template", F4_PROMPT_TEMPLATE),
        ]:
            existing = db.execute(
                __import__("sqlalchemy").text(
                    "SELECT key FROM system_settings WHERE key = :key"
                ),
                {"key": key},
            ).fetchone()
            if existing:
                logger.info("システム設定 '%s' は既に登録済みです", key)
            else:
                db.execute(
                    __import__("sqlalchemy").text(
                        "INSERT INTO system_settings (key, value, updated_at) "
                        "VALUES (:key, :value, :updated_at)"
                    ),
                    {"key": key, "value": value, "updated_at": now},
                )
                logger.info("システム設定 '%s' を登録しました", key)

        # --- 初期管理者ユーザー作成 ---
        existing_user = db.execute(
            __import__("sqlalchemy").text(
                "SELECT username FROM users WHERE username = :username"
            ),
            {"username": username},
        ).fetchone()
        if existing_user:
            logger.info("ユーザー '%s' は既に登録済みです", username)
        else:
            encrypted_key = _encrypt_virtual_key(virtual_key, encryption_key_b64)
            password_hash = _hash_password(password)
            db.execute(
                __import__("sqlalchemy").text(
                    "INSERT INTO users "
                    "(username, email, virtual_key_encrypted, default_cli, default_model, "
                    "role, is_active, password_hash, system_mcp_enabled, created_at, updated_at) "
                    "VALUES (:username, :email, :vk, :default_cli, :default_model, "
                    "'admin', true, :pw_hash, true, :created_at, :updated_at)"
                ),
                {
                    "username": username,
                    "email": email,
                    "vk": encrypted_key,
                    "default_cli": default_cli,
                    "default_model": default_model,
                    "pw_hash": password_hash,
                    "created_at": now,
                    "updated_at": now,
                },
            )
            logger.info("管理者ユーザー '%s' を作成しました", username)

        db.commit()
        logger.info("セットアップが正常に完了しました")

    except Exception as exc:
        db.rollback()
        logger.error("セットアップ中にエラーが発生しました: %s", exc)
        sys.exit(1)
    finally:
        db.close()


# -----------------------------------------------------------------------
# エントリーポイント
# -----------------------------------------------------------------------

def main() -> None:
    """コマンドライン引数またはインタラクティブ入力でパラメータを受け取る"""
    parser = argparse.ArgumentParser(
        description="CodingAgentAutomata セットアップスクリプト"
    )
    parser.add_argument("--username", help="管理者GitLabユーザー名")
    parser.add_argument("--email", help="管理者メールアドレス")
    parser.add_argument("--password", help="管理者パスワード")
    parser.add_argument("--virtual-key", dest="virtual_key", help="LiteLLM Virtual Key")
    parser.add_argument("--default-cli", dest="default_cli", help="デフォルトCLIエージェントID")
    parser.add_argument("--default-model", dest="default_model", help="デフォルトモデル名")
    args = parser.parse_args()

    # 対話入力（引数が省略された場合）
    username = args.username or input("管理者ユーザー名: ").strip()
    email = args.email or input("メールアドレス: ").strip()
    password = args.password or getpass.getpass("パスワード: ")
    virtual_key = args.virtual_key or getpass.getpass("LiteLLM Virtual Key: ")
    default_cli = args.default_cli or input("デフォルトCLI (例: claude): ").strip()
    default_model = args.default_model or input("デフォルトモデル (例: claude-opus-4-5): ").strip()

    setup(username, email, password, virtual_key, default_cli, default_model)


if __name__ == "__main__":
    main()
