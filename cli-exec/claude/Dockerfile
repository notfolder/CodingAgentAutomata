# Claude Code cli-exec コンテナイメージ
# CLI コンテナの共通の土台（cli-exec/base。ビルドコンテキスト base）の上に Claude Code を入れる。
FROM base

# Claude Code CLI インストール
RUN npm install -g @anthropic-ai/claude-code@latest

# 追加環境のビルド時埋め込み（例: "apt-get update && apt-get install -y --no-install-recommends golang ruby"）
ARG EXTRA_SETUP_COMMANDS=""
RUN if [ -n "$EXTRA_SETUP_COMMANDS" ]; then sh -c "$EXTRA_SETUP_COMMANDS"; fi

# Claude Code CLI は root での --dangerously-skip-permissions 使用を禁止するため、利用者 claude で実行する
ENV CLI_RUN_AS=claude
# /workspace のオーナーを claude ユーザーにする（opencode 用は root のまま）
RUN chown claude:claude /workspace

WORKDIR /workspace
