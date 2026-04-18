# opencode cli-exec コンテナイメージ
# DinD（Docker-in-Docker）構成で opencode CLI を実行する

FROM docker:26-dind

# 必要なツールのインストール
RUN apk add --no-cache \
    curl \
    git \
    nodejs \
    npm \
    python3 \
    py3-pip \
    bash \
    jq

# uv (Pythonパッケージマネージャー) インストール
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Playwright インストール
RUN npm install -g playwright@latest

# opencode CLI インストール
RUN npm install -g opencode-ai@latest

# 追加環境のビルド時埋め込み
ARG EXTRA_SETUP_COMMANDS=""
RUN if [ -n "$EXTRA_SETUP_COMMANDS" ]; then sh -c "$EXTRA_SETUP_COMMANDS"; fi

WORKDIR /workspace
