#!/bin/bash
# テスト環境セットアップスクリプト
set -e

# スクリプトが存在するディレクトリの親（プロジェクトルート）を基準にする
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# .env ファイルが存在する場合は読み込む（既に設定済みの環境変数は上書きしない）
ENV_FILE="${PROJECT_ROOT}/.env"
if [ -f "${ENV_FILE}" ]; then
    echo ".env を読み込みます: ${ENV_FILE}"
    set -o allexport
    # コメント行と空行を除いて読み込む
    # shellcheck disable=SC1090
    source <(grep -v '^\s*#' "${ENV_FILE}" | grep -v '^\s*$')
    set +o allexport
else
    echo "警告: .env が見つかりません（${ENV_FILE}）。環境変数を直接設定してください。"
fi

echo "テスト環境セットアップを開始します..."

# 依存ライブラリをインストールする（venv を使用して外部管理環境の制限を回避）
VENV_DIR="${PROJECT_ROOT}/.venv-test-setup"
if [ ! -d "${VENV_DIR}" ]; then
    python3 -m venv "${VENV_DIR}"
fi
"${VENV_DIR}/bin/pip" install requests -q

# CLIイメージ（claude / opencode）をビルドする
echo "CLIイメージをビルドします..."
docker compose --profile build-only build

# GitLab コンテナから Producer の Webhook エンドポイントへ到達するには
# Docker ネットワーク内部のサービス名を使用する必要がある
export WEBHOOK_URL="${WEBHOOK_URL:-http://producer:8080/webhook}"
# test_setup.py はホストマシン上で実行するため localhost を使用する
export BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"

"${VENV_DIR}/bin/python3" scripts/test_setup.py "$@"
echo "テスト環境セットアップが完了しました。"
