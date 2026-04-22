#!/bin/bash
# テスト環境セットアップスクリプト
# 使い方:
#   ./scripts/test_setup.sh              # モック LLM モード（実 API キー不要）
#   ./scripts/test_setup.sh --real       # 実 LLM モード（ANTHROPIC_API_KEY / OPENAI_API_KEY 必要）
#   ./scripts/test_setup.sh --run-tests  # セットアップ後に E2E テストも実行する
set -e

# スクリプトが存在するディレクトリの親（プロジェクトルート）を基準にする
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# オプション解析
REAL_LLM=false
RUN_TESTS=false
for arg in "$@"; do
    case "$arg" in
        --real) REAL_LLM=true ;;
        --run-tests) RUN_TESTS=true ;;
    esac
done

# -------------------------------------------------------
# ステップ 0: .env が存在しない場合は .env.example から生成する
# -------------------------------------------------------
ENV_FILE="${PROJECT_ROOT}/.env"
ENV_EXAMPLE="${PROJECT_ROOT}/.env.example"

if [ ! -f "${ENV_FILE}" ]; then
    echo "[ステップ 0] .env が存在しないため .env.example をコピーして生成します..."
    if [ ! -f "${ENV_EXAMPLE}" ]; then
        echo "エラー: .env.example が見つかりません: ${ENV_EXAMPLE}" >&2
        exit 1
    fi
    cp "${ENV_EXAMPLE}" "${ENV_FILE}"

    # 固定値を自動設定する
    # ENCRYPTION_KEY（32バイト乱数を base64 エンコード）
    GENERATED_ENCRYPTION_KEY=$(python3 -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())")
    # JWT_SECRET_KEY（64バイト乱数を hex エンコード）
    GENERATED_JWT_SECRET=$(python3 -c "import os; print(os.urandom(64).hex())")
    # GITLAB_WEBHOOK_SECRET
    GENERATED_WEBHOOK_SECRET=$(python3 -c "import os; print(os.urandom(16).hex())")

    sed -i.bak \
        -e "s|^ENCRYPTION_KEY=.*|ENCRYPTION_KEY=${GENERATED_ENCRYPTION_KEY}|" \
        -e "s|^JWT_SECRET_KEY=.*|JWT_SECRET_KEY=${GENERATED_JWT_SECRET}|" \
        -e "s|^GITLAB_WEBHOOK_SECRET=.*|GITLAB_WEBHOOK_SECRET=${GENERATED_WEBHOOK_SECRET}|" \
        -e "s|^GITLAB_PAT=.*|GITLAB_PAT=placeholder_replaced_by_test_setup|" \
        -e "s|^GITLAB_API_URL=.*|GITLAB_API_URL=http://localhost:8929|" \
        -e "s|^LITELLM_MASTER_KEY=.*|LITELLM_MASTER_KEY=sk-litellm-master-e2e-test|" \
        "${ENV_FILE}"
    rm -f "${ENV_FILE}.bak"

    echo ".env を生成しました: ${ENV_FILE}"
    echo "  ENCRYPTION_KEY, JWT_SECRET_KEY, GITLAB_WEBHOOK_SECRET を自動生成しました"
    echo "  GITLAB_API_URL=http://localhost:8929, LITELLM_MASTER_KEY=sk-litellm-master-e2e-test を設定しました"
    echo "  ※ ANTHROPIC_API_KEY / OPENAI_API_KEY を使用する場合は .env に設定してください"
fi

# -------------------------------------------------------
# .env を読み込む（既に設定済みの環境変数は上書きしない）
# -------------------------------------------------------
echo ".env を読み込みます: ${ENV_FILE}"
set -o allexport
# shellcheck disable=SC1090
source <(grep -v '^\s*#' "${ENV_FILE}" | grep -v '^\s*$')
set +o allexport

echo "テスト環境セットアップを開始します..."

# -------------------------------------------------------
# ステップ 1: CLI イメージをビルドする
# -------------------------------------------------------
echo ""
echo "[ステップ 1] CLI イメージ（claude / opencode）をビルドします..."
docker compose --profile build-only build

# -------------------------------------------------------
# ステップ 2: テスト環境のサービスを起動する
# -------------------------------------------------------
echo ""
if [ "${REAL_LLM}" = "true" ]; then
    COMPOSE_PROFILE="test-real"
    PLAYWRIGHT_SERVICE="test_playwright_real"
else
    COMPOSE_PROFILE="test"
    PLAYWRIGHT_SERVICE="test_playwright"
fi

echo "[ステップ 2] サービスを起動します（profile: ${COMPOSE_PROFILE}）..."
docker compose --profile "${COMPOSE_PROFILE}" up -d --build

# -------------------------------------------------------
# ステップ 3: Backend の起動と Alembic マイグレーション
# -------------------------------------------------------
echo ""
echo "[ステップ 3] Backend の起動を待機し Alembic マイグレーションを実行します..."
BACKEND_READY=false
for i in $(seq 1 30); do
    if curl -sf http://localhost:8000/health 2>/dev/null; then
        BACKEND_READY=true
        break
    fi
    echo "  Backend 起動待ち... (${i}/30)"
    sleep 5
done

if [ "${BACKEND_READY}" = "false" ]; then
    echo "エラー: Backend が起動しませんでした（150秒タイムアウト）" >&2
    exit 1
fi
echo "  Backend 起動確認済み"

# Alembic マイグレーション（リトライあり）
echo "  Alembic マイグレーションを実行します..."
ALEMBIC_SUCCESS=false
for i in $(seq 1 5); do
    if docker compose run --rm -T backend sh -c "cd /app/backend && alembic upgrade head" 2>&1; then
        ALEMBIC_SUCCESS=true
        break
    fi
    echo "  Alembic マイグレーション失敗 (試行 ${i}/5), 5秒後に再試行します..."
    sleep 5
done
if [ "${ALEMBIC_SUCCESS}" = "false" ]; then
    echo "エラー: Alembic マイグレーションに失敗しました" >&2
    exit 1
fi

# -------------------------------------------------------
# ステップ 4: setup.py（管理者ユーザー・CLIアダプタ登録）
# -------------------------------------------------------
echo ""
echo "[ステップ 4] setup.py を実行します（管理者ユーザー・CLIアダプタ登録）..."
SETUP_SUCCESS=false
for i in $(seq 1 3); do
    if docker compose run --rm -T backend \
        sh -c "cd /app && python scripts/setup.py \
            --username admin \
            --email admin@example.com \
            --password Admin@123456 \
            --virtual-key sk-placeholder \
            --default-cli claude \
            --default-model claude-3-haiku-20240307"; then
        SETUP_SUCCESS=true
        break
    fi
    echo "  setup.py 失敗 (試行 ${i}/3), 5秒後に再試行します..."
    sleep 5
done
if [ "${SETUP_SUCCESS}" = "false" ]; then
    echo "エラー: setup.py の実行に失敗しました" >&2
    exit 1
fi

# 管理者ログイン確認
echo "  管理者ログインを確認します..."
ADMIN_LOGIN_OK=false
for i in $(seq 1 10); do
    LOGIN_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/api/auth/login \
        -H "Content-Type: application/json" \
        -d '{"username":"admin","password":"Admin@123456"}' 2>/dev/null)
    if [ "${LOGIN_STATUS}" = "200" ]; then
        ADMIN_LOGIN_OK=true
        echo "  管理者ログイン確認済み (HTTP 200)"
        break
    fi
    echo "  管理者ログイン確認待ち... (${i}/10, HTTP ${LOGIN_STATUS})"
    sleep 3
done
if [ "${ADMIN_LOGIN_OK}" = "false" ]; then
    echo "エラー: 管理者ログインに失敗しました（admin/Admin@123456）" >&2
    docker compose logs backend | tail -20 >&2
    exit 1
fi

# --real モード時は LiteLLM Proxy（litellm_real）の起動を待機する
if [ "${REAL_LLM}" = "true" ]; then
    echo ""
    echo "[ステップ 4.5] LiteLLM Proxy（litellm_real）の起動を待機します..."
    LITELLM_READY=false
    for i in $(seq 1 30); do
        HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:4001/health 2>/dev/null || true)
        # 200（認証不要）または 401（認証必要だがサーバーは起動中）のいずれもOK
        if [ "${HTTP_STATUS}" = "200" ] || [ "${HTTP_STATUS}" = "401" ]; then
            LITELLM_READY=true
            echo "  LiteLLM Proxy 起動確認済み (HTTP ${HTTP_STATUS})"
            break
        fi
        echo "  LiteLLM Proxy 起動待ち... (${i}/30, HTTP ${HTTP_STATUS})"
        sleep 5
    done
    if [ "${LITELLM_READY}" = "false" ]; then
        echo "  警告: LiteLLM Proxy が応答しませんでした。フォールバックモードで続行します。" >&2
    fi
fi

# -------------------------------------------------------
# ステップ 5: test_setup.py（GitLab・テストユーザー設定）
# -------------------------------------------------------
echo ""
echo "[ステップ 5] test_setup.py を実行します（GitLab・テストユーザー設定）..."

# 依存ライブラリをインストールする（venv を使用して外部管理環境の制限を回避）
VENV_DIR="${PROJECT_ROOT}/.venv-test-setup"
if [ ! -d "${VENV_DIR}" ]; then
    python3 -m venv "${VENV_DIR}"
fi
"${VENV_DIR}/bin/pip" install requests -q

# GitLab コンテナから Producer の Webhook エンドポイントへ到達するには
# Docker ネットワーク内部のサービス名を使用する必要がある
export WEBHOOK_URL="${WEBHOOK_URL:-http://producer:8080/webhook}"
# test_setup.py はホストマシン上で実行するため localhost を使用する
export BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
# test_setup.py はホストマシン上で実行するため、LiteLLM / モック LLM はホスト公開ポートを使用する
# （.env の Docker 内部 URL を上書き）
export LITELLM_PROXY_URL="http://localhost:4001"
export MOCK_LLM_URL="http://localhost:4000"
# .env の source が子プロセスに渡らない場合に備え LITELLM_MASTER_KEY を明示的に export する
if [ -z "${LITELLM_MASTER_KEY:-}" ]; then
    LITELLM_MASTER_KEY=$(grep '^LITELLM_MASTER_KEY=' "${ENV_FILE}" | cut -d'=' -f2- | tr -d '\r')
fi
export LITELLM_MASTER_KEY

"${VENV_DIR}/bin/python3" "${SCRIPT_DIR}/test_setup.py"

# -------------------------------------------------------
# ステップ 6: .env.test の内容を反映するためサービスを force-recreate
# -------------------------------------------------------
echo ""
echo "[ステップ 6] .env.test の内容を反映するため producer / consumer を再起動します..."
docker compose up -d --force-recreate producer consumer

echo ""
echo "テスト環境セットアップが完了しました。"

# -------------------------------------------------------
# ステップ 7（オプション）: E2E テスト実行
# -------------------------------------------------------
if [ "${RUN_TESTS}" = "true" ]; then
    echo ""
    echo "[ステップ 7] E2E テストを実行します（Playwright: ${PLAYWRIGHT_SERVICE}）..."
    docker compose run --rm "${PLAYWRIGHT_SERVICE}" sh -c "npm install --silent && npx playwright test 2>&1"
fi
