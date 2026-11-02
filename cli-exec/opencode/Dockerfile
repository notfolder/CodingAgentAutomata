# opencode cli-exec コンテナイメージ
# CLI コンテナの共通の土台（cli-exec/base。ビルドコンテキスト base）の上に opencode を入れる。
FROM base

# opencode CLI インストール
RUN npm install -g opencode-ai@latest

# opencode の wrapper script (node/bun 経由) を native binary を直接呼ぶ shell script に置き換える
# wrapper script 経由だと bun が 'run "prompt"' を 'bun run "prompt"' として解釈するため
RUN NATIVE_BIN=$(find "$(npm root -g)/opencode-ai/node_modules" -name opencode -not -name "*.js" -path "*/bin/*" 2>/dev/null | head -1) && \
    if [ -n "$NATIVE_BIN" ]; then \
        printf '#!/bin/sh\nexec "%s" "$@"\n' "$NATIVE_BIN" > /usr/local/bin/opencode && \
        chmod +x /usr/local/bin/opencode; \
    fi

# 追加環境のビルド時埋め込み（例: "apt-get update && apt-get install -y --no-install-recommends golang ruby"）
ARG EXTRA_SETUP_COMMANDS=""
RUN if [ -n "$EXTRA_SETUP_COMMANDS" ]; then sh -c "$EXTRA_SETUP_COMMANDS"; fi

WORKDIR /workspace
