#!/bin/bash
# システムセットアップスクリプト
# Usage: ./scripts/setup.sh [--username U --email E --password P --virtual-key K --default-cli C --default-model M]
set -e

# スクリプトが存在するディレクトリの親（プロジェクトルート）を基準にする
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "CodingAgentAutomata セットアップを開始します..."

echo "[ステップ 1/2] CLI イメージ（claude / opencode）をビルドします..."
if ! ./scripts/build_cli_exec.sh 2>&1; then
	echo "エラー: CLI イメージのビルドに失敗しました。セットアップを中断します。" >&2
	echo "ヒント: buildx builder で security.insecure entitlement の許可が必要です。" >&2
	exit 1
fi

echo "[ステップ 2/2] バックエンド初期設定を実行します..."
docker compose exec -T backend python /app/scripts/setup.py "$@"
echo "セットアップが完了しました。"
