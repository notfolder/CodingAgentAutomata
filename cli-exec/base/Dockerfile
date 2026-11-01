# CLI コンテナの共通の土台イメージ（Claude Code 用・opencode 用の両方が使う）
# Ubuntu 24.04 に、中の Docker デーモン・Node.js・Python と uv・Playwright とブラウザの依存物・証明書の道具を入れる。
# Playwright の標準のブラウザ（Chromium 系と WebKit）が動く土台にする。
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# Docker Engine と、コンテナ内で Docker デーモンを動かす起動用スクリプト（moby の hack/dind）の版
ARG DOCKER_VERSION=29.9.2
ARG DIND_SCRIPT_SHA256=673bb7adc8b463b56e9e929672ea74b40951f655a023d0b9801f46c9da4bc509
ARG NODE_MAJOR=24

# Zscaler の証明書を OS の信頼先に入れる（外へ出る最初の処理より前。無効なら何もしない）
RUN --mount=type=bind,from=zscaler,target=/zscaler sh /zscaler/install-ca.sh
# 各ツールの信頼先を OS の証明書の束に向ける（Zscaler 設定の有効・無効によらない）
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt \
    NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt

# 基本の道具（ca-certificates を入れると、入れておいた Zscaler の証明書も OS の束に入る）
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg git jq bash iptables libnss3-tools \
        python3 python3-pip python3-venv xz-utils procps util-linux \
    && rm -rf /var/lib/apt/lists/*

# Docker Engine（Docker 公式の apt から、版を固定して入れる）
RUN install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc \
    && chmod a+r /etc/apt/keyrings/docker.asc \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu noble stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && DOCKER_PKG_VERSION="$(apt-cache madison docker-ce | awk '{print $3}' | grep "^5:${DOCKER_VERSION}-" | head -1)" \
    && test -n "${DOCKER_PKG_VERSION}" \
    && apt-get install -y --no-install-recommends \
        docker-ce="${DOCKER_PKG_VERSION}" docker-ce-cli="${DOCKER_PKG_VERSION}" \
        containerd.io docker-buildx-plugin docker-compose-plugin \
    && ln -s /usr/libexec/docker/cli-plugins/docker-compose /usr/local/bin/docker-compose \
    && rm -rf /var/lib/apt/lists/*

# コンテナ内で Docker デーモンを動かす起動用スクリプト（チェックサムで確かめる）
RUN curl -fsSL "https://raw.githubusercontent.com/moby/moby/docker-v${DOCKER_VERSION}/hack/dind" -o /usr/local/bin/dind \
    && echo "${DIND_SCRIPT_SHA256}  /usr/local/bin/dind" | sha256sum -c - \
    && chmod +x /usr/local/bin/dind

# Node.js（NodeSource の apt）
RUN curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" -o /tmp/nodesource_setup.sh \
    && bash /tmp/nodesource_setup.sh \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* /tmp/nodesource_setup.sh

# uv（どの利用者からも使えるよう /usr/local/bin に置く）
RUN curl -LsSf https://astral.sh/uv/install.sh -o /tmp/uv_install.sh \
    && UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh /tmp/uv_install.sh \
    && rm -f /tmp/uv_install.sh

# Playwright と、Chromium・WebKit の依存物（ブラウザ本体は対象リポジトリの版に合わせて実行時に取得する）
RUN npm install -g playwright@latest \
    && npx playwright install-deps chromium webkit \
    && rm -rf /var/lib/apt/lists/*

# CLI を実行する利用者 claude（docker グループに入れる）。/workspace の持ち主は各 CLI のイメージで決める
RUN useradd -m -s /bin/bash claude \
    && usermod -aG docker claude \
    && mkdir -p /workspace

# Chromium 系が読む利用者ごとの証明書データベースに Zscaler の証明書を入れる（無効なら何もしない）
RUN --mount=type=bind,from=zscaler,target=/zscaler \
    sh /zscaler/install-ca.sh nss root /root \
    && sh /zscaler/install-ca.sh nss claude /home/claude

# 起動処理
COPY dind-start.sh /usr/local/bin/dind-start.sh
RUN chmod +x /usr/local/bin/dind-start.sh

# 中の Docker デーモンのデータはボリュームに置く（コンテナの overlay の上に overlay を重ねられないため）
VOLUME /var/lib/docker

WORKDIR /workspace

ENTRYPOINT ["/usr/local/bin/dind-start.sh"]
