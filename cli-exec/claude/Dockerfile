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
    jq \
    docker-compose

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

# 起動時ブロッキングを避けるため、dockerd をバックグラウンド起動して
# 即座に CMD を実行するカスタム entrypoint を配置
RUN cat <<'EOF' > /usr/local/bin/dind-start.sh
#!/bin/sh
set -eu

dockerd >/tmp/dockerd.log 2>&1 &
exec "$@"
EOF
RUN chmod +x /usr/local/bin/dind-start.sh

# ビルド時に一度 dockerd を起動し、必要ファイルの初期化を済ませる
RUN sh -c 'dockerd >/tmp/dockerd-build.log 2>&1 & pid=$!; sleep 10; kill "$pid" || true; wait "$pid" || true'

# 非 root ユーザーを作成（Claude Code CLI は root での --dangerously-skip-permissions 使用を禁止するため）
RUN addgroup -S claude && adduser -S -G claude claude
# docker グループへのアクセスを付与（DinD 構成で docker コマンドを使用する場合に必要）
RUN addgroup claude ping || true

# /workspace のオーナーを claude ユーザーに変更
RUN mkdir -p /workspace && chown claude:claude /workspace
# uv のパスを非 root ユーザーでも使えるように
ENV PATH="/root/.local/bin:$PATH"

USER claude
WORKDIR /workspace

ENTRYPOINT ["/usr/local/bin/dind-start.sh"]
CMD ["sleep", "infinity"]
