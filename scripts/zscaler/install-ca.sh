#!/bin/sh
# イメージ内の Zscaler 証明書の導入処理（イメージのビルド中に実行する。POSIX sh）
# 準備処理が .zscaler/ へ写したものを、Dockerfile がビルドコンテキスト zscaler としてマウントして実行する。
# 使い方:
#   sh /zscaler/install-ca.sh                 OS の信頼先に入れる
#   sh /zscaler/install-ca.sh nss <利用者> <ホーム>  利用者の Chromium 系の証明書データベースに入れる
set -eu

DIR="$(cd "$(dirname "$0")" && pwd)"
STATE="$(cat "${DIR}/state" 2>/dev/null || true)"
MODE="${1:-system}"

case "${STATE}" in
    disabled)
        # Zscaler 設定が無効なら何もしない
        exit 0
        ;;
    enabled)
        ;;
    *)
        echo "エラー: Zscaler 設定の準備ができていません（state が無い）。./scripts/compose.sh などのスクリプトからビルドしてください。" >&2
        exit 1
        ;;
esac

# PEM の束を 1 証明書ずつのファイルに分ける。引数: <束> <出力ファイルの接頭辞>
split_certs() {
    awk -v prefix="$2" '
        /-----BEGIN CERTIFICATE-----/ { n++; file = sprintf("%s-%03d.crt", prefix, n) }
        n > 0 { print > file }
        /-----END CERTIFICATE-----/ { close(file) }
    ' "$1"
}

install_system() {
    # ビルドにプロキシの宛先が渡されていなければ止める
    if [ -z "${HTTPS_PROXY:-}${https_proxy:-}" ]; then
        echo "エラー: Zscaler 設定が有効ですが、ビルドにプロキシの宛先が渡されていません。./scripts/compose.sh などのスクリプトからビルドしてください。" >&2
        exit 1
    fi
    mkdir -p /usr/local/share/ca-certificates
    cp "${DIR}/extra-ca.pem" /usr/local/share/ca-certificates/zscaler.crt
    if command -v update-ca-certificates >/dev/null 2>&1; then
        # Debian・Ubuntu
        update-ca-certificates >/dev/null
    elif [ -f /etc/ssl/certs/ca-certificates.crt ]; then
        # update-ca-certificates の無い土台（Alpine など）は束に足す
        cat "${DIR}/extra-ca.pem" >> /etc/ssl/certs/ca-certificates.crt
    else
        # ca-certificates が未導入の土台。後で ca-certificates を入れると zscaler.crt も束に入る
        mkdir -p /etc/ssl/certs
        cat "${DIR}/extra-ca.pem" > /etc/ssl/certs/ca-certificates.crt
    fi
    echo "Zscaler の証明書を OS の信頼先に入れました"
}

install_nss() {
    user="$1"
    home="$2"
    if ! command -v certutil >/dev/null 2>&1; then
        echo "エラー: certutil がありません（libnss3-tools を入れてください）" >&2
        exit 1
    fi
    work="$(mktemp -d)"
    split_certs "${DIR}/extra-ca.pem" "${work}/zscaler"
    # Chromium は版によって 2 か所のどちらかの証明書データベースを読む
    for db in "${home}/.pki/nssdb" "${home}/.local/share/pki/nssdb"; do
        mkdir -p "${db}"
        if [ ! -f "${db}/cert9.db" ]; then
            certutil -N -d "sql:${db}" --empty-password
        fi
        for cert in "${work}"/zscaler-*.crt; do
            [ -f "${cert}" ] || continue
            certutil -A -d "sql:${db}" -n "$(basename "${cert}" .crt)" -t "C,," -i "${cert}"
        done
    done
    rm -rf "${work}"
    chown -R "${user}:" "${home}/.pki" "${home}/.local"
    echo "Zscaler の証明書を ${user} の証明書データベースに入れました"
}

case "${MODE}" in
    system)
        install_system
        ;;
    nss)
        install_nss "$2" "$3"
        ;;
    *)
        echo "エラー: 使い方: install-ca.sh [nss <利用者> <ホーム>]" >&2
        exit 1
        ;;
esac
