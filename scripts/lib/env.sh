#!/bin/bash
# .env の読み込み（複数のスクリプトで共通に使う）
# 使い方: source scripts/lib/env.sh; load_env_file <ファイル>

# KEY=VALUE 形式の行を読み、環境変数として export する。
# コメント行と空行は読み飛ばし、末尾の CR と値を囲むダブルクォートを取り除く。
# 既にある環境変数は、ファイルの値で上書きする。
load_env_file() {
    local file_path="$1"
    if [ ! -f "${file_path}" ]; then
        return 0
    fi

    while IFS= read -r line || [ -n "${line}" ]; do
        # コメント行と空行をスキップ
        case "${line}" in
            ''|'#'*)
                continue
                ;;
        esac

        # KEY=VALUE 形式のみ受け付ける
        if [[ "${line}" != *=* ]]; then
            continue
        fi

        local key="${line%%=*}"
        local value="${line#*=}"

        # 末尾CRを除去
        key="${key%$'\r'}"
        value="${value%$'\r'}"

        # 既存のダブルクォートを剥がす
        if [[ "${value}" == \"*\" && "${value}" == *\" ]]; then
            value="${value#\"}"
            value="${value%\"}"
        fi

        export "${key}=${value}"
    done < "${file_path}"
}

# .env の 1 つの項目の値を返す（ファイルに無ければ何も出さない。同じ項目が複数あれば最後のもの）。
# 環境変数は書き換えない。
read_env_value() {
    local file_path="$1"
    local wanted="$2"
    if [ ! -f "${file_path}" ]; then
        return 0
    fi
    local line key value found=""
    while IFS= read -r line || [ -n "${line}" ]; do
        case "${line}" in
            ''|'#'*) continue ;;
        esac
        [[ "${line}" != *=* ]] && continue
        key="${line%%=*}"
        key="${key%$'\r'}"
        if [ "${key}" = "${wanted}" ]; then
            value="${line#*=}"
            value="${value%$'\r'}"
            if [[ "${value}" == \"*\" && "${value}" == *\" ]]; then
                value="${value#\"}"
                value="${value%\"}"
            fi
            found="${value}"
        fi
    done < "${file_path}"
    printf '%s' "${found}"
}
