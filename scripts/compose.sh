#!/bin/bash
# compose の入口スクリプト
# 使い方: ./scripts/compose.sh <docker compose の引数>（例: ./scripts/compose.sh up -d --build）
# Zscaler 設定の準備を行い、ビルド用の値を環境に入れてから docker compose を実行する。
# 準備に失敗したら docker compose は実行せず、同じ終了コードで終わる。
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"
# shellcheck source=lib/env.sh
source "${SCRIPT_DIR}/lib/env.sh"
# shellcheck source=lib/zscaler.sh
source "${SCRIPT_DIR}/lib/zscaler.sh"

zscaler_prepare || exit $?
zscaler_export_build_env "${PROJECT_ROOT}"

cd "${PROJECT_ROOT}"
exec docker compose "$@"
