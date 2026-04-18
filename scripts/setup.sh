#!/bin/bash
# システムセットアップスクリプト
# Usage: ./scripts/setup.sh [--username U --email E --password P --virtual-key K --default-cli C --default-model M]
set -e

echo "CodingAgentAutomata セットアップを開始します..."
docker compose exec -T backend python /app/scripts/setup.py "$@"
echo "セットアップが完了しました。"
