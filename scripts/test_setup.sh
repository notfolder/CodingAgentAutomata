#!/bin/bash
# テスト環境セットアップスクリプト
set -e

echo "テスト環境セットアップを開始します..."
python3 scripts/test_setup.py "$@"
echo "テスト環境セットアップが完了しました。"
