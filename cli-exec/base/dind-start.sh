#!/bin/sh
# CLI コンテナの起動処理
# 中の Docker デーモンを後ろで起動してから、指定されたコマンドを実行する。
# CLI_RUN_AS が指定されていれば、その利用者に切り替えてコマンドを実行する。
# 引数が無ければ、Docker デーモンのログを表示し続ける。
set -eu

# Zscaler 設定が有効なら、root と claude の Docker クライアントの設定にプロキシを書く。
# 中のコンテナは CLI コンテナの名前解決を使えないので、プロキシのホスト名は IP アドレスに解決して書く。
configure_inner_docker_proxy() {
    if [ "${ZSCALER_ENABLED:-false}" != "true" ] || [ -z "${HTTPS_PROXY:-}" ]; then
        return 0
    fi
    proxy="${HTTPS_PROXY}"
    proxy_host="$(printf '%s' "${proxy}" | sed -E 's#^[a-zA-Z]+://([^:/]+).*#\1#')"
    proxy_ip="$(getent hosts "${proxy_host}" | awk '{print $1; exit}' || true)"
    if [ -n "${proxy_ip}" ]; then
        inner_proxy="$(printf '%s' "${proxy}" | sed "s#//${proxy_host}#//${proxy_ip}#")"
    else
        echo "警告: プロキシのホスト名 ${proxy_host} を解決できませんでした。中のコンテナ向けにはホスト名のまま書きます" >&2
        inner_proxy="${proxy}"
    fi
    no_proxy_value="${NO_PROXY:-}"
    for home_dir in /root /home/claude; do
        [ -d "${home_dir}" ] || continue
        mkdir -p "${home_dir}/.docker"
        cat > "${home_dir}/.docker/config.json" <<EOF
{
  "proxies": {
    "default": {
      "httpProxy": "${inner_proxy}",
      "httpsProxy": "${inner_proxy}",
      "noProxy": "${no_proxy_value}"
    }
  }
}
EOF
    done
    if [ -d /home/claude/.docker ]; then
        chown -R claude:claude /home/claude/.docker
    fi
}

# iptables の方式を選ぶ（nftables が使えないカーネルでは legacy に切り替える）
select_iptables() {
    if ! iptables -nL >/dev/null 2>&1; then
        if command -v iptables-legacy >/dev/null 2>&1 && iptables-legacy -nL >/dev/null 2>&1; then
            update-alternatives --set iptables /usr/sbin/iptables-legacy >/dev/null 2>&1 || true
            update-alternatives --set ip6tables /usr/sbin/ip6tables-legacy >/dev/null 2>&1 || true
        fi
    fi
}

# /tmp を先に tmpfs にして、中身（consumer が起動前に書き込むプロンプトと起動コマンド）を戻す。
# 起動用スクリプト dind は /tmp が tmpfs でなければ被せて中身を隠すため、先に被せておく。
prepare_tmp() {
    if mountpoint -q /tmp; then
        return 0
    fi
    saved="$(mktemp -d /run/tmp-saved.XXXXXX)"
    cp -a /tmp/. "${saved}/"
    # 特権の無いコンテナでは被せられない（その場合は Docker デーモンも動かないので、そのまま進む）
    if mount -t tmpfs -o mode=1777 none /tmp 2>/dev/null; then
        cp -a "${saved}/." /tmp/
    fi
    rm -rf "${saved}"
}

configure_inner_docker_proxy
select_iptables
prepare_tmp

# 中の Docker デーモンを後ろで起動する（環境変数のプロキシはそのまま引き継ぐ）
dind dockerd >/tmp/dockerd.log 2>&1 &

if [ "$#" -eq 0 ]; then
    exec tail -f /tmp/dockerd.log
fi

if [ -n "${CLI_RUN_AS:-}" ] && [ "$(id -u)" = "0" ]; then
    run_home="$(getent passwd "${CLI_RUN_AS}" | cut -d: -f6)"
    exec setpriv --reuid="${CLI_RUN_AS}" --regid="${CLI_RUN_AS}" --init-groups \
        env HOME="${run_home}" USER="${CLI_RUN_AS}" "$@"
fi

exec "$@"
