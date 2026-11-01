#!/bin/bash
# Zscaler 設定の準備処理（関数群）
# 使い方: source scripts/lib/env.sh; source scripts/lib/zscaler.sh; zscaler_prepare [--mock] [--project-dir DIR] [--host-bundle FILE]
#
# .env の Zscaler 設定と証明書から、各部品が使う生成物を .zscaler/ に作る。
# 生成物: state、extra-ca.pem（有効なときだけ）、ca-bundle.pem、install-ca.sh、zscaler.env、build.env
# macOS 標準の bash 3.2 でも動くように書く。

ZSCALER_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 除外宛先に自動で入れる、本システムの compose のサービス名とネットワークの別名
ZSCALER_SERVICE_NAMES="postgresql postgresql_litellm rabbitmq backend frontend producer consumer mock_llm gitlab litellm litellm_real test_playwright test_playwright_real cli_exec_base cli_exec_claude cli_exec_opencode unit_test"
# ホストの OS の証明書の束を探す順番
ZSCALER_HOST_BUNDLE_CANDIDATES="/etc/ssl/certs/ca-certificates.crt /etc/pki/tls/certs/ca-bundle.crt /etc/ssl/cert.pem"
# 模擬プロキシの宛先（ビルドと実行中の部品は compose の追加のホスト名、ホストで行う接続確認と pip は 127.0.0.1）
ZSCALER_MOCK_BUILD_PROXY="http://host.docker.internal:18080"
ZSCALER_MOCK_RUNTIME_PROXY="http://host.docker.internal:18080"
ZSCALER_MOCK_HOST_PROXY="http://127.0.0.1:18080"
# 使用前の接続確認でつなぐ外部の HTTPS
ZSCALER_PREFLIGHT_URL="https://pypi.org/simple/"

# エラーを標準エラーに出す。
zscaler_err() {
    echo "エラー: $*" >&2
}

# 設定の値を返す。環境変数にあればそれを、無ければ .env の値を使う。
# 引数: <項目名> <.env のパス>
zscaler_setting() {
    local name="$1"
    local env_file="$2"
    local value="${!name:-}"
    if [ -n "${value}" ]; then
        printf '%s' "${value}"
    else
        read_env_value "${env_file}" "${name}"
    fi
}

# ホストの OS の証明書の束のパスを返す（見つからなければ何も出さない）。
# 引数: [差し替えのパス]（テスト用。指定されたらそのファイルだけを見る）
zscaler_find_host_bundle() {
    local override="${1:-}"
    local candidate
    if [ -n "${override}" ]; then
        if [ -f "${override}" ]; then
            printf '%s' "${override}"
        fi
        return 0
    fi
    for candidate in ${ZSCALER_HOST_BUNDLE_CANDIDATES}; do
        if [ -f "${candidate}" ]; then
            printf '%s' "${candidate}"
            return 0
        fi
    done
}

# ファイルが PEM 形式の証明書を 1 つ以上含むかを返す。
zscaler_has_cert() {
    [ -f "$1" ] && grep -q -- "-----BEGIN CERTIFICATE-----" "$1"
}

# Zscaler 設定の必須チェック。足りなければ原因と外し方を出して 1 を返す。
# 引数: <有効・無効の値> <プロキシの宛先> <証明書ファイル> <ホストの OS の束（無ければ空）>
zscaler_require_settings() {
    local enabled="$1"
    local proxy="$2"
    local cert_file="$3"
    local host_bundle="$4"

    case "${enabled}" in
        true|false) ;;
        *)
            zscaler_err "ZSCALER_ENABLED の値「${enabled}」は使えません。true か false を書いてください。"
            return 1
            ;;
    esac
    if [ "${enabled}" = "false" ]; then
        return 0
    fi
    if [ -z "${proxy}" ]; then
        zscaler_err "Zscaler 設定が有効ですが、プロキシの宛先 ZSCALER_PROXY_URL がありません。.env に http://ホスト名:ポート の形で書いてください。Zscaler を使わない環境では、.env に ZSCALER_ENABLED=false と書くと外せます。"
        return 1
    fi
    if ! printf '%s' "${proxy}" | grep -Eq '^http://[^/:@]+:[0-9]+/?$'; then
        zscaler_err "ZSCALER_PROXY_URL「${proxy}」の形が正しくありません。http://ホスト名:ポート の形で書いてください。Zscaler を使わない環境では、.env に ZSCALER_ENABLED=false と書くと外せます。"
        return 1
    fi
    if ! zscaler_has_cert "${cert_file}" && [ -z "${host_bundle}" ]; then
        zscaler_err "Zscaler の証明書がありません。${cert_file} に PEM 形式で置くか、ホストの OS の信頼先に入れてください。Zscaler を使わない環境では、.env に ZSCALER_ENABLED=false と書くと外せます。"
        return 1
    fi
    return 0
}

# 除外宛先の一覧を返す（カンマ区切り。重複は除く）。
# 引数: <社内の除外宛先（カンマ区切り。空でよい）>
zscaler_build_no_proxy() {
    local extra="$1"
    local result=""
    local item
    local IFS_SAVED="${IFS}"
    for item in localhost 127.0.0.1 ::1 ${ZSCALER_SERVICE_NAMES}; do
        result="${result},${item}"
    done
    IFS=','
    for item in ${extra}; do
        # 前後の空白を取り除く
        item="$(printf '%s' "${item}" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
        if [ -z "${item}" ]; then
            continue
        fi
        case ",${result#,}," in
            *",${item},"*) ;;
            *) result="${result},${item}" ;;
        esac
    done
    IFS="${IFS_SAVED}"
    printf '%s' "${result#,}"
}

# 使用前の接続確認。プロキシ経由で外部の HTTPS につなぎ、証明書の束で検証できるかを確かめる。
# 引数: <プロキシの宛先> <証明書の束>
zscaler_preflight() {
    local proxy="$1"
    local bundle="$2"
    local rc=0
    curl -sS -I -o /dev/null --max-time 20 --noproxy "" --proxy "${proxy}" --cacert "${bundle}" "${ZSCALER_PREFLIGHT_URL}" 2>/dev/null || rc=$?
    case "${rc}" in
        0)
            return 0
            ;;
        35|51|58|60|77|83|90|91)
            zscaler_err "使用前の接続確認に失敗しました（証明書を検証できない）。プロキシ ${proxy} 経由で ${ZSCALER_PREFLIGHT_URL} の証明書を、証明書の束で検証できませんでした。Zscaler の証明書を確かめてください。"
            ;;
        5|6|7|28|56|97)
            zscaler_err "使用前の接続確認に失敗しました（プロキシに接続できない）。プロキシ ${proxy} に接続できないか、時間切れになりました。ZSCALER_PROXY_URL を確かめてください。"
            ;;
        *)
            zscaler_err "使用前の接続確認に失敗しました（curl の終了コード ${rc}）。プロキシ ${proxy} 経由で ${ZSCALER_PREFLIGHT_URL} につなげませんでした。"
            ;;
    esac
    return 1
}

# 準備処理の本体。生成物を一時ディレクトリに作ってから .zscaler/ と置き換える。
# 引数: [--mock] [--project-dir DIR] [--host-bundle FILE]
zscaler_prepare() {
    local mock=false
    local project_dir=""
    local host_override=""
    while [ $# -gt 0 ]; do
        case "$1" in
            --mock) mock=true ;;
            --project-dir) shift; project_dir="${1:-}" ;;
            --host-bundle) shift; host_override="${1:-}" ;;
            *)
                zscaler_err "準備処理の引数「$1」は使えません。"
                return 1
                ;;
        esac
        shift
    done
    if [ -z "${project_dir}" ]; then
        project_dir="$(cd "${ZSCALER_LIB_DIR}/../.." && pwd)"
    fi

    # 呼び出し元で同じプロジェクトの準備が済んでいれば繰り返さない
    if [ "${ZSCALER_PREPARED:-}" = "1" ] && [ "${ZSCALER_PREPARED_DIR:-}" = "${project_dir}" ]; then
        return 0
    fi

    local env_file="${project_dir}/.env"
    local cert_file="${project_dir}/certs/zscaler-ca.pem"
    local enabled build_proxy runtime_proxy host_proxy extra host_bundle
    extra="$(zscaler_setting ZSCALER_NO_PROXY_EXTRA "${env_file}")"
    host_bundle="$(zscaler_find_host_bundle "${host_override}")"

    if [ "${mock}" = "true" ]; then
        enabled=true
        cert_file="${project_dir}/zscaler-mock/.data/mitmproxy-ca-cert.pem"
        build_proxy="${ZSCALER_MOCK_BUILD_PROXY}"
        runtime_proxy="${ZSCALER_MOCK_RUNTIME_PROXY}"
        host_proxy="${ZSCALER_MOCK_HOST_PROXY}"
        if ! zscaler_has_cert "${cert_file}"; then
            zscaler_err "模擬プロキシの認証局の証明書がありません: ${cert_file}"
            return 1
        fi
    else
        enabled="$(zscaler_setting ZSCALER_ENABLED "${env_file}")"
        enabled="${enabled:-true}"
        build_proxy="$(zscaler_setting ZSCALER_PROXY_URL "${env_file}")"
        build_proxy="${build_proxy%/}"
        runtime_proxy="${build_proxy}"
        host_proxy="${build_proxy}"
        zscaler_require_settings "${enabled}" "${build_proxy}" "${cert_file}" "${host_bundle}" || return 1
    fi

    local tmp_dir
    tmp_dir="$(mktemp -d "${project_dir}/.zscaler.tmp.XXXXXX")" || return 1

    if [ "${enabled}" = "true" ]; then
        local no_proxy
        no_proxy="$(zscaler_build_no_proxy "${extra}")"
        if zscaler_has_cert "${cert_file}"; then
            cp "${cert_file}" "${tmp_dir}/extra-ca.pem"
            if [ -n "${host_bundle}" ]; then
                cat "${cert_file}" "${host_bundle}" > "${tmp_dir}/ca-bundle.pem"
            else
                cp "${cert_file}" "${tmp_dir}/ca-bundle.pem"
            fi
            echo "[Zscaler] 証明書: ${cert_file}"
        else
            cp "${host_bundle}" "${tmp_dir}/extra-ca.pem"
            cp "${host_bundle}" "${tmp_dir}/ca-bundle.pem"
            echo "[Zscaler] 証明書: ホストの OS の束（${host_bundle}）"
        fi
        echo "[Zscaler] 使用前の接続確認を行います（${host_proxy} 経由で ${ZSCALER_PREFLIGHT_URL}）..."
        if ! zscaler_preflight "${host_proxy}" "${tmp_dir}/ca-bundle.pem"; then
            rm -rf "${tmp_dir}"
            return 1
        fi
        echo "enabled" > "${tmp_dir}/state"
        {
            echo "ZSCALER_ENABLED=true"
            echo "HTTP_PROXY=${runtime_proxy}"
            echo "HTTPS_PROXY=${runtime_proxy}"
            echo "http_proxy=${runtime_proxy}"
            echo "https_proxy=${runtime_proxy}"
            echo "NO_PROXY=${no_proxy}"
            echo "no_proxy=${no_proxy}"
        } > "${tmp_dir}/zscaler.env"
        {
            echo "ZSCALER_BUILD_PROXY=${build_proxy}"
            echo "ZSCALER_BUILD_NO_PROXY=${no_proxy}"
            echo "ZSCALER_HOST_PROXY=${host_proxy}"
        } > "${tmp_dir}/build.env"
    else
        if [ -z "${host_bundle}" ]; then
            zscaler_err "ホストの OS の証明書の束が見つかりません（${ZSCALER_HOST_BUNDLE_CANDIDATES}）。"
            rm -rf "${tmp_dir}"
            return 1
        fi
        cp "${host_bundle}" "${tmp_dir}/ca-bundle.pem"
        echo "disabled" > "${tmp_dir}/state"
        echo "ZSCALER_ENABLED=false" > "${tmp_dir}/zscaler.env"
        {
            echo "ZSCALER_BUILD_PROXY="
            echo "ZSCALER_BUILD_NO_PROXY="
            echo "ZSCALER_HOST_PROXY="
        } > "${tmp_dir}/build.env"
        echo "[Zscaler] Zscaler 設定は無効です（証明書とプロキシを使いません）"
    fi
    cp "${ZSCALER_LIB_DIR}/../zscaler/install-ca.sh" "${tmp_dir}/install-ca.sh"

    rm -rf "${project_dir}/.zscaler"
    mv "${tmp_dir}" "${project_dir}/.zscaler"
    export ZSCALER_PREPARED=1
    export ZSCALER_PREPARED_DIR="${project_dir}"
    echo "[Zscaler] 準備ができました: ${project_dir}/.zscaler"
    return 0
}

# build.env の値（ビルド用のプロキシの宛先と除外宛先、ホストで使うプロキシの宛先）を、呼び出し元の環境に入れる。
# 引数: [プロジェクトのディレクトリ]
zscaler_export_build_env() {
    local project_dir="${1:-$(cd "${ZSCALER_LIB_DIR}/../.." && pwd)}"
    local build_env="${project_dir}/.zscaler/build.env"
    ZSCALER_BUILD_PROXY="$(read_env_value "${build_env}" ZSCALER_BUILD_PROXY)"
    ZSCALER_BUILD_NO_PROXY="$(read_env_value "${build_env}" ZSCALER_BUILD_NO_PROXY)"
    ZSCALER_HOST_PROXY="$(read_env_value "${build_env}" ZSCALER_HOST_PROXY)"
    export ZSCALER_BUILD_PROXY ZSCALER_BUILD_NO_PROXY ZSCALER_HOST_PROXY
}
