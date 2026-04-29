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
# スペースを含む値を正しく扱うため KEY="VALUE" 形式に変換してから読み込む
source <(grep -v '^\s*#' "${ENV_FILE}" | grep -v '^\s*$' | sed 's/^\([^=]*\)=\(.*\)$/\1="\2"/')
set +o allexport

# GitLab コンテナ名（.env 未設定時は docker-compose の既定名を使用）
GITLAB_CONTAINER="${GITLAB_CONTAINER:-codingagentautomata-gitlab-1}"

echo "テスト環境セットアップを開始します..."

# -------------------------------------------------------
# ステップ 1: テスト環境のサービスを起動する
# -------------------------------------------------------
echo ""
if [ "${REAL_LLM}" = "true" ]; then
    COMPOSE_PROFILE="test-real"
    PLAYWRIGHT_SERVICE="test_playwright_real"
else
    COMPOSE_PROFILE="test"
    PLAYWRIGHT_SERVICE="test_playwright"
fi

echo "[ステップ 1] サービスを起動します（profile: ${COMPOSE_PROFILE}）..."
docker compose --profile "${COMPOSE_PROFILE}" up -d --build

# -------------------------------------------------------
# ステップ 1.5: GitLab root パスワードを変更する
# -------------------------------------------------------
echo ""
echo "[ステップ 1.5] GitLab root パスワードを変更します..."
# 本システムの管理者パスワードと同じ固定値を使用
GITLAB_ROOT_PASSWORD="Admin@123456"

# GitLab の共通パスワード判定に該当する固定値を許容するため、テスト環境では validation を無効化して保存する
RUBY_SCRIPT="user = User.find_by_username('root'); user.password = '${GITLAB_ROOT_PASSWORD}'; user.password_confirmation = '${GITLAB_ROOT_PASSWORD}'; user.save!(validate: false); puts 'Root password changed successfully'"

# GitLab コンテナの起動を待機しながらパスワード変更を試みる
PASSWORD_CHANGED=false
for i in $(seq 1 30); do
    if docker exec "${GITLAB_CONTAINER}" gitlab-rails runner "${RUBY_SCRIPT}"; then
        PASSWORD_CHANGED=true
        echo "  GitLab root パスワードを変更しました: ${GITLAB_ROOT_PASSWORD}"
        break
    fi
    echo "  GitLab root パスワード変更待機中... (${i}/30)"
    sleep 5
done

if [ "${PASSWORD_CHANGED}" = "false" ]; then
    echo "  警告: GitLab root パスワードの変更に失敗しました"
fi

# -------------------------------------------------------
# ステップ 2: Backend の起動と Alembic マイグレーション
# -------------------------------------------------------
echo ""
echo "[ステップ 2] Backend の起動を待機し Alembic マイグレーションを実行します..."
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
    if docker compose exec -T backend sh -c "cd /app/backend && alembic upgrade head" 2>&1; then
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
# ステップ 3: setup.sh（CLI イメージビルド + 管理者ユーザー・CLIアダプタ登録）
# -------------------------------------------------------
echo ""
echo "[ステップ 3] setup.sh を実行します（CLI イメージビルド + 管理者ユーザー・CLIアダプタ登録）..."
SETUP_SUCCESS=false
for i in $(seq 1 3); do
    if ./scripts/setup.sh \
        --username admin \
        --email admin@example.com \
        --password Admin@123456 \
        --virtual-key sk-placeholder \
        --default-cli claude \
        --default-model "${DEFAULT_CLAUDE_MODEL:-claude-haiku-4-5-20251001}"; then
        SETUP_SUCCESS=true
        break
    fi
    echo "  setup.sh 失敗 (試行 ${i}/3), 5秒後に再試行します..."
    sleep 5
done
if [ "${SETUP_SUCCESS}" = "false" ]; then
    echo "エラー: setup.sh の実行に失敗しました" >&2
    exit 1
fi

echo "  setup.py による必須システム設定（F-3/F-4）を確認します..."
DB_USER="${POSTGRES_USER:-user}"
DB_NAME="${POSTGRES_DB:-db}"

TEMPLATE_VALID_COUNT=$(docker compose exec -T postgresql psql -U "${DB_USER}" -d "${DB_NAME}" -At -c "
SELECT COUNT(*)
    FROM system_settings
 WHERE key IN ('f3_prompt_template', 'f4_prompt_template')
     AND value IS NOT NULL
     AND value <> '';
")

if [ "${TEMPLATE_VALID_COUNT}" != "2" ]; then
        echo "エラー: 必須テンプレート設定が不足しています（f3/f4）" >&2
        echo "  現在値を表示します:" >&2
        docker compose exec -T postgresql psql -U "${DB_USER}" -d "${DB_NAME}" -P pager=off -c "
SELECT key,
             CASE
                 WHEN value IS NULL THEN '<NULL>'
                 WHEN value = '' THEN '<EMPTY>'
                 ELSE '<SET>'
             END AS value_state
    FROM system_settings
 WHERE key IN ('f3_prompt_template', 'f4_prompt_template')
 ORDER BY key;
" >&2
        exit 1
fi
echo "  必須システム設定 f3/f4 を確認しました"

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
# GitLab テストユーザー（testuser-claude / testuser-opencode）の固定パスワード
export TEST_USER_PASSWORD="${TEST_USER_PASSWORD:-Test@123456}"
# .env の source が子プロセスに渡らない場合に備え LITELLM_MASTER_KEY を明示的に export する
if [ -z "${LITELLM_MASTER_KEY:-}" ]; then
    LITELLM_MASTER_KEY=$(grep '^LITELLM_MASTER_KEY=' "${ENV_FILE}" | cut -d'=' -f2- | tr -d '\r')
fi
export LITELLM_MASTER_KEY

"${VENV_DIR}/bin/python3" "${SCRIPT_DIR}/test_setup.py"

# -------------------------------------------------------
# ステップ 5.5: GitLab テストユーザーのパスワードを固定化
# -------------------------------------------------------
echo ""
echo "[ステップ 5.5] GitLab テストユーザーのパスワードを固定化します..."

# GitLab rails 環境が応答することを確認（最大30秒待機）
echo "  GitLab rails 環境の準備を確認中..."
RAILS_READY=false
for i in $(seq 1 30); do
    if docker exec "${GITLAB_CONTAINER}" gitlab-rails runner "puts 'OK'" >/dev/null 2>&1; then
        RAILS_READY=true
        echo "  GitLab rails 環境: 準備完了"
        break
    fi
    echo "  GitLab rails 環境: 起動待機中... (${i}/30)"
    sleep 1
done

if [ "${RAILS_READY}" = "false" ]; then
    echo "エラー: GitLab rails 環境が応答しません（最大30秒待機）" >&2
    docker exec "${GITLAB_CONTAINER}" gitlab-rails runner "puts 'test'" 2>&1 | head -20 >&2
    exit 1
fi

# 各テストユーザーのパスワード設定
for gitlab_user in testuser-claude testuser-opencode; do
    echo "  ${gitlab_user} のパスワード設定処理を開始..."
    
    # Ruby スクリプトを整形して実行（エラー出力を完全に記録）
    # 処理内容: ユーザー検索 → パスワード設定 → 保存 → 検証
    RUBY_SCRIPT=$(cat <<'RUBY_EOF'
user = User.find_by_username('GITLAB_USER')
if user.nil?
  STDERR.puts("ERROR: ユーザーが見つかりません: GITLAB_USER")
  exit 11
end

# パスワード設定
user.password = 'TEST_PASSWORD'
user.password_confirmation = 'TEST_PASSWORD'
user.password_automatically_set = false if user.respond_to?(:password_automatically_set=)

# 保存（検証スキップ）
unless user.save!(validate: false)
  STDERR.puts("ERROR: ユーザーの保存に失敗しました: #{user.errors.full_messages.join(', ')}")
  exit 12
end

# パスワード検証
unless user.valid_password?('TEST_PASSWORD')
  STDERR.puts("ERROR: パスワード検証に失敗しました（保存されたが検証に失敗）")
  exit 13
end

puts "SUCCESS: #{user.username} のパスワードを正常に設定しました"
RUBY_EOF
)
    
    # プレースホルダーを置換
    RUBY_SCRIPT="${RUBY_SCRIPT//GITLAB_USER/$gitlab_user}"
    RUBY_SCRIPT="${RUBY_SCRIPT//TEST_PASSWORD/$TEST_USER_PASSWORD}"
    
    # スクリプト実行（stderr と stdout を両方記録）
    SETUP_OUTPUT=$(docker exec "${GITLAB_CONTAINER}" gitlab-rails runner "${RUBY_SCRIPT}" 2>&1)
    SETUP_EXIT_CODE=$?
    
    # 実行結果の判定と詳細出力
    if [ ${SETUP_EXIT_CODE} -eq 0 ]; then
        echo "  ✓ ${gitlab_user}: パスワード設定成功"
        echo "    ${SETUP_OUTPUT}"
    else
        echo "エラー: ${gitlab_user} のパスワード設定に失敗しました (exit code: ${SETUP_EXIT_CODE})" >&2
        echo "  出力内容:" >&2
        echo "${SETUP_OUTPUT}" | sed 's/^/    /' >&2
        exit 1
    fi
done

echo "  全テストユーザーのパスワード設定が完了しました"

# -------------------------------------------------------
# ステップ 6: .env.test の内容を反映するためサービスを force-recreate
# -------------------------------------------------------
echo ""
echo "[ステップ 6] .env.test の内容を反映するため producer / consumer を再起動します..."
docker compose up -d --force-recreate producer consumer

echo ""
echo "テスト環境セットアップが完了しました。"

# -------------------------------------------------------
# 補助: テスト実行の前後でキュー/タスク状態をクリーンアップする
# -------------------------------------------------------
cleanup_test_runtime_state() {
    local phase="$1"

    echo ""
    echo "[クリーンアップ:${phase}] consumer停止 → キュー掃除 → pending/running整理 → consumer再起動 を実行します..."

    # クリーンアップ失敗で本処理を止めないように一時的にerrexitを無効化
    set +e

    # 1) consumer 停止（処理中タスクの再配信状態を作る）
    docker compose stop consumer >/dev/null 2>&1
    if [ $? -eq 0 ]; then
        echo "  consumer を停止しました"
    else
        echo "  警告: consumer の停止に失敗しました（続行）" >&2
    fi

    # 2) RabbitMQ tasks キューをパージ
    local rabbitmq_user="${RABBITMQ_DEFAULT_USER:-guest}"
    local rabbitmq_pass="${RABBITMQ_DEFAULT_PASS:-guest}"
    local rabbitmq_mgmt_url="${RABBITMQ_MGMT_URL:-http://localhost:15672}"
    local queue_status
    queue_status=$(curl -s -o /dev/null -w "%{http_code}" -u "${rabbitmq_user}:${rabbitmq_pass}" \
        -X DELETE "${rabbitmq_mgmt_url}/api/queues/%2F/tasks/contents")
    if [ "${queue_status}" = "200" ] || [ "${queue_status}" = "204" ]; then
        echo "  RabbitMQ tasks キューをパージしました (HTTP ${queue_status})"
    else
        echo "  警告: RabbitMQ tasks キューのパージに失敗しました (HTTP ${queue_status})" >&2
    fi

    # 3) DB の pending/running タスクを failed に更新
    local db_user="${POSTGRES_USER:-user}"
    local db_name="${POSTGRES_DB:-db}"
    local db_update_output
    db_update_output=$(docker compose exec -T postgresql psql -U "${db_user}" -d "${db_name}" -At -c "
WITH updated AS (
  UPDATE tasks
     SET status = 'failed',
         error_message = CASE
           WHEN error_message IS NULL OR error_message = '' THEN '[test-cleanup] テストクリーンアップにより強制終了扱いにしました'
           ELSE error_message || E'\\n[test-cleanup] テストクリーンアップにより強制終了扱いにしました'
         END,
         completed_at = NOW()
   WHERE status IN ('pending', 'running')
 RETURNING 1
)
SELECT COUNT(*) FROM updated;
")
    if [ $? -eq 0 ]; then
        echo "  pending/running タスクを failed 化しました: ${db_update_output}件"
    else
        echo "  警告: pending/running タスクの整理に失敗しました（続行）" >&2
    fi

    # 4) consumer 再起動
    docker compose up -d consumer >/dev/null 2>&1
    if [ $? -eq 0 ]; then
        echo "  consumer を再起動しました"
    else
        echo "  警告: consumer の再起動に失敗しました（続行）" >&2
    fi

    # 元のerrexit動作に戻す
    set -e
}

# -------------------------------------------------------
# ステップ 7（オプション）: E2E テスト実行
# -------------------------------------------------------
if [ "${RUN_TESTS}" = "true" ]; then
    echo ""
    echo "[ステップ 7] E2E テストを実行します（Playwright: ${PLAYWRIGHT_SERVICE}）..."

    # テスト前にキュー/タスク状態を明示的にクリーンアップ
    cleanup_test_runtime_state "テスト実行前"

    # テスト失敗時も後処理を実行できるように一時的にerrexitを無効化
    set +e
    docker compose run --rm "${PLAYWRIGHT_SERVICE}" sh -c "npm install --silent && npx playwright test 2>&1"
    PLAYWRIGHT_EXIT_CODE=$?
    set -e

    # テスト後にもキュー/タスク状態をクリーンアップ（次回実行への持ち越し防止）
    cleanup_test_runtime_state "テスト実行後"

    if [ ${PLAYWRIGHT_EXIT_CODE} -ne 0 ]; then
        echo "エラー: E2E テストが失敗しました (exit code: ${PLAYWRIGHT_EXIT_CODE})" >&2
        exit ${PLAYWRIGHT_EXIT_CODE}
    fi
fi
