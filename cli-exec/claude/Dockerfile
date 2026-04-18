# Claude Code cli-exec コンテナイメージ
# DinD（Docker-in-Docker）構成で Claude Code CLI を実行する

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

# Claude Code CLI インストール
RUN npm install -g @anthropic-ai/claude-code@latest

# 追加環境のビルド時埋め込み（例: "apk add rust go ruby"）
ARG EXTRA_SETUP_COMMANDS=""
RUN if [ -n "$EXTRA_SETUP_COMMANDS" ]; then sh -c "$EXTRA_SETUP_COMMANDS"; fi

WORKDIR /workspace
