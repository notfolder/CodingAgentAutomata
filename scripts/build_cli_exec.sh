#!/bin/bash
# cli-exec イメージをビルドするスクリプト
# Zscaler 設定の準備を行ってから、compose の定義（共通の土台と Claude Code 用・opencode 用）でビルドする。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=lib/env.sh
source "${SCRIPT_DIR}/lib/env.sh"
# shellcheck source=lib/zscaler.sh
source "${SCRIPT_DIR}/lib/zscaler.sh"

cd "${PROJECT_ROOT}"

zscaler_prepare
zscaler_export_build_env "${PROJECT_ROOT}"

echo "[1/1] cli-exec の共通の土台・claude・opencode のイメージをビルドします..."
docker compose --profile build-only build cli_exec_base cli_exec_claude cli_exec_opencode

echo "cli-exec イメージのビルドが完了しました。"
