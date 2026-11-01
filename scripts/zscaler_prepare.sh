#!/bin/bash
# Zscaler 設定の準備処理のコマンド
# 使い方: ./scripts/zscaler_prepare.sh [--mock] [--project-dir DIR] [--host-bundle FILE]
#   --mock         模擬プロキシの値を使う（テスト環境用）
#   --project-dir  .env・certs・.zscaler を置くディレクトリ（テスト用。既定はこのリポジトリ）
#   --host-bundle  ホストの OS の証明書の束の代わりに使うファイル（テスト用）
# 終了コード: 成功 0、失敗 1
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/env.sh
source "${SCRIPT_DIR}/lib/env.sh"
# shellcheck source=lib/zscaler.sh
source "${SCRIPT_DIR}/lib/zscaler.sh"

# コマンドとして呼ばれたときは、毎回準備し直す
unset ZSCALER_PREPARED ZSCALER_PREPARED_DIR
zscaler_prepare "$@" || exit 1
exit 0
