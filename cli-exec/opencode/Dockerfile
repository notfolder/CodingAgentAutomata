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
    jq \
    gcompat

# uv (Pythonパッケージマネージャー) インストール
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Playwright インストール
RUN npm install -g playwright@latest

# opencode CLI インストール
RUN npm install -g opencode-ai@latest

# opencode の wrapper script (node/bun 経由) を native binary を直接呼ぶ shell script に置き換える
# wrapper script 経由だと bun が 'run "prompt"' を 'bun run "prompt"' として解釈するため
RUN NATIVE_BIN=$(find /usr/local/lib/node_modules/opencode-ai/node_modules -name opencode -not -name "*.js" -path "*/bin/*" 2>/dev/null | head -1) && \
    if [ -n "$NATIVE_BIN" ]; then \
        printf '#!/bin/sh\nexec "%s" "$@"\n' "$NATIVE_BIN" > /usr/local/bin/opencode && \
        chmod +x /usr/local/bin/opencode; \
    fi

# 追加環境のビルド時埋め込み
ARG EXTRA_SETUP_COMMANDS=""
RUN if [ -n "$EXTRA_SETUP_COMMANDS" ]; then sh -c "$EXTRA_SETUP_COMMANDS"; fi

WORKDIR /workspace
