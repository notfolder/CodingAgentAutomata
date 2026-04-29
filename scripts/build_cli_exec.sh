#!/bin/bash
# cli-exec イメージを BuildKit の security.insecure 許可付きでビルドするスクリプト
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_ROOT}"

echo "[1/2] cli-exec-claude イメージをビルドします..."
docker buildx build \
  --allow security.insecure \
  --load \
  -t coding-agent-cli-exec-claude:latest \
  cli-exec/claude/

echo "[2/2] cli-exec-opencode イメージをビルドします..."
docker buildx build \
  --allow security.insecure \
  --load \
  -t coding-agent-cli-exec-opencode:latest \
  cli-exec/opencode/

echo "cli-exec イメージのビルドが完了しました。"
