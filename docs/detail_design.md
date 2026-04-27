# CodingAgentAutomata 詳細設計書

この文書は、現行リポジトリ実装に基づく詳細設計書である。要件上の理想形ではなく、2026年4月24日時点でリポジトリに存在する実装内容と運用前提を記載する。

## 1. 言語・フレームワーク

| 対象 | 採用技術 | 補足 |
| --- | --- | --- |
| バックエンドAPI | Python 3.12 / FastAPI | 管理API、認証、設定管理を担当する |
| Producer | Python 3.12 / aiohttp | Webhook受信とポーリングを担当する |
| Consumer | Python 3.12 / asyncio | RabbitMQからのタスク処理を担当する |
| フロントエンド | Vue 3 / TypeScript / Vuetify / Pinia | 管理画面を担当する |
| フロント配信 | nginx | Vueビルド成果物の配信と /api 逆プロキシを担当する |
| データベース | PostgreSQL 16 | アプリケーションデータ永続化を担当する |
| メッセージキュー | RabbitMQ 3.13 | ProducerとConsumerの疎通を担当する |
| E2Eテスト | Playwright | docker compose上でGUI操作を行う |

### 1.1 フロントエンドとAPIの接続

- フロントエンドは nginx 配下で配信される
- APIリクエストは /api 配下へ送信する
- FastAPI 側は各ルーターを /api プレフィックスで登録する
- フロントエンドの axios クライアントは /api を baseURL とする

## 2. システム構成

### 2.1 コンポーネント一覧

| コンポーネント | 役割 | 常時利用 |
| --- | --- | --- |
| frontend | 管理画面配信、/api 逆プロキシ | はい |
| backend | 認証、ユーザー管理、タスク一覧、設定管理API | はい |
| producer | GitLab Webhook受信、GitLabポーリング、タスク投入 | はい |
| consumer | タスク処理、CLIコンテナ管理、進捗報告 | はい |
| postgresql | users、tasks、cli_adapters、system_settings の保持 | はい |
| rabbitmq | tasks キューの保持 | はい |
| postgresql_litellm | LiteLLM 用DB | テスト系のみ |
| mock_llm | モックLLMサーバー | test プロファイル |
| gitlab | GitLab CE テスト環境 | test / test-real プロファイル |
| litellm | モックLLMを背後に持つ LiteLLM Proxy | test プロファイル |
| litellm_real | 実LLMを背後に持つ LiteLLM Proxy | test-real プロファイル |
| test_playwright | Playwright 実行コンテナ | test プロファイル |
| test_playwright_real | Playwright 実行コンテナ | test-real プロファイル |
| cli_exec_claude | Claude系 CLI イメージビルド用サービス | build-only プロファイル |
| cli_exec_opencode | opencode CLI イメージビルド用サービス | build-only プロファイル |

### 2.2 全体構成図

```mermaid
graph TB
    subgraph External
        Browser[ブラウザ]
        GitLabExt[GitLab API / GitLab Webhook]
        LLM[LiteLLM Proxy]
    end

    subgraph DockerCompose
        Frontend[frontend: nginx + Vue]
        Backend[backend: FastAPI]
        Producer[producer]
        Consumer[consumer]
        Postgres[(postgresql)]
        Rabbit[(rabbitmq)]
        CliExec[cli-exec 動的コンテナ]

        subgraph TestProfile
            GitLabCE[gitlab]
            MockLLM[mock_llm]
            LiteLLM[litellm / litellm_real]
            PW[test_playwright / test_playwright_real]
            LiteDB[(postgresql_litellm)]
        end
    end

    Browser --> Frontend
    Frontend -->|/api| Backend
    Producer --> GitLabExt
    GitLabExt -->|Webhook| Producer
    Producer --> Rabbit
    Consumer --> Rabbit
    Consumer --> CliExec
    CliExec --> LLM
    Backend --> Postgres
    Producer --> Postgres
    Consumer --> Postgres
    LiteLLM --> LiteDB
    LiteLLM --> MockLLM
    PW --> Frontend
    PW --> Backend
    PW --> GitLabCE
```

### 2.3 ネットワーク構成

- すべてのサービスは codingagent_net 上で接続する
- frontend は 80 番ポートを公開する
- backend は 8000 番ポートを公開する
- producer はコンテナ内で GitLab Webhook を受ける HTTP 待受を行う（docker-compose では producer の待受ポートをホスト公開しない）
- rabbitmq は 5672 と 15672 を公開する
- postgresql は 5432 を公開する
- consumer は docker.sock をマウントし、動的に CLI コンテナを起動する

## 3. データベース設計

### 3.1 アプリケーションDBの対象

アプリケーション本体では PostgreSQL を使用する。永続化対象は users、cli_adapters、tasks、system_settings の4テーブルである。

LiteLLM 用の postgresql_litellm は本体DBとは独立したテスト系補助DBであり、本節の業務データ設計対象には含めない。

### 3.2 テーブル一覧

| テーブル名 | 役割 |
| --- | --- |
| users | システム利用者、認証情報、Virtual Key、既定CLI設定を保持する |
| cli_adapters | 利用可能なCLIアダプタ設定を保持する |
| tasks | Issue/MR処理の状態と実行ログを保持する |
| system_settings | F-3/F-4テンプレートと system_mcp_config を保持する |

### 3.3 users

| カラム名 | 型 | 制約 | 説明 |
| --- | --- | --- | --- |
| username | VARCHAR(255) | PK | ユーザー名 |
| email | VARCHAR(255) | UNIQUE, NOT NULL | メールアドレス |
| virtual_key_encrypted | BYTEA | NOT NULL | 暗号化済み Virtual Key |
| default_cli | VARCHAR(255) | FK cli_adapters.cli_id, NOT NULL | 既定CLI |
| default_model | VARCHAR(255) | NOT NULL | 既定モデル |
| role | VARCHAR(20) | CHECK admin/user, NOT NULL | 権限 |
| is_active | BOOLEAN | NOT NULL | 有効フラグ |
| password_hash | VARCHAR(255) | NOT NULL | bcrypt ハッシュ |
| system_mcp_enabled | BOOLEAN | NOT NULL | システムMCP適用フラグ |
| user_mcp_config | JSONB | NULL | ユーザー個別MCP設定 |
| f4_prompt_template | TEXT | NULL | ユーザー個別F-4テンプレート |
| created_at | TIMESTAMPTZ | NOT NULL | 作成日時 |
| updated_at | TIMESTAMPTZ | NOT NULL | 更新日時 |

### 3.4 cli_adapters

| カラム名 | 型 | 制約 | 説明 |
| --- | --- | --- | --- |
| cli_id | VARCHAR(255) | PK | CLI識別子 |
| container_image | VARCHAR(512) | NOT NULL | 実行イメージ |
| start_command_template | TEXT | NOT NULL | 起動コマンドテンプレート |
| env_mappings | JSONB | NOT NULL | 環境変数マッピング |
| config_content_env | VARCHAR(255) | NULL | 設定JSONを渡す環境変数名 |
| is_builtin | BOOLEAN | NOT NULL | 組み込みフラグ |
| created_at | TIMESTAMPTZ | NOT NULL | 作成日時 |
| updated_at | TIMESTAMPTZ | NOT NULL | 更新日時 |

### 3.5 tasks

| カラム名 | 型 | 制約 | 説明 |
| --- | --- | --- | --- |
| task_uuid | UUID | PK | タスク識別子 |
| task_type | VARCHAR(50) | CHECK issue/merge_request, NOT NULL | タスク種別 |
| gitlab_project_id | BIGINT | NOT NULL | GitLabプロジェクトID |
| source_iid | BIGINT | NOT NULL | Issue IID または MR IID |
| username | VARCHAR(255) | FK users.username, NOT NULL | 処理対象ユーザー |
| status | VARCHAR(20) | CHECK pending/running/completed/failed, NOT NULL | 状態 |
| cli_type | VARCHAR(255) | FK cli_adapters.cli_id, NULL | 実行CLI |
| model | VARCHAR(255) | NULL | 実行モデル |
| cli_log | TEXT | NULL | 実行ログ |
| error_message | TEXT | NULL | エラー内容 |
| created_at | TIMESTAMPTZ | NOT NULL | 作成日時 |
| started_at | TIMESTAMPTZ | NULL | 開始日時 |
| completed_at | TIMESTAMPTZ | NULL | 完了日時 |

同一の gitlab_project_id、source_iid、task_type に対して、status が pending または running の行が複数存在しないように部分ユニークインデックスを作成する。

### 3.6 system_settings

| カラム名 | 型 | 制約 | 説明 |
| --- | --- | --- | --- |
| key | VARCHAR(255) | PK | 設定キー |
| value | TEXT | NOT NULL | 設定値 |
| updated_at | TIMESTAMPTZ | NOT NULL | 更新日時 |

管理対象キーは以下の3件である。

| キー | 用途 |
| --- | --- |
| f3_prompt_template | Issue から MR を生成するプロンプトテンプレート |
| f4_prompt_template | MR 処理の既定テンプレート |
| system_mcp_config | システム共通 MCP 設定 |

### 3.7 ER図

```mermaid
erDiagram
    users ||--o{ tasks : username
    cli_adapters ||--o{ users : default_cli
    cli_adapters ||--o{ tasks : cli_type

    users {
        VARCHAR username PK
        VARCHAR email UK
        BYTEA virtual_key_encrypted
        VARCHAR default_cli FK
        VARCHAR default_model
        VARCHAR role
        BOOLEAN is_active
        VARCHAR password_hash
        BOOLEAN system_mcp_enabled
        JSONB user_mcp_config
        TEXT f4_prompt_template
    }

    cli_adapters {
        VARCHAR cli_id PK
        VARCHAR container_image
        TEXT start_command_template
        JSONB env_mappings
        VARCHAR config_content_env
        BOOLEAN is_builtin
    }

    tasks {
        UUID task_uuid PK
        VARCHAR task_type
        BIGINT gitlab_project_id
        BIGINT source_iid
        VARCHAR username FK
        VARCHAR status
        VARCHAR cli_type FK
        VARCHAR model
        TEXT cli_log
        TEXT error_message
    }

    system_settings {
        VARCHAR key PK
        TEXT value
    }
```

### 3.8 業務エンティティ一覧

| エンティティ | 一覧 | 詳細 | 作成 | 更新 | 削除 | 検索 | 状態管理 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| users | あり | あり | あり | あり | あり | username 前方一致 | is_active による有効/無効 |
| cli_adapters | あり | 一覧ベース | あり | あり | あり | cli_id 単位 | is_builtin は保護属性であり業務状態ではない |
| tasks | あり | 専用詳細APIなし | Producer が作成 | Consumer が更新 | なし | username, status, task_type | pending, running, completed, failed |
| system_settings | なし | 一括取得 | 初期化時に投入 | あり | なし | キー単位 | 業務状態は持たない |

### 3.9 エンティティ対応関係

| エンティティ | 画面 | API | 主担当クラス |
| --- | --- | --- | --- |
| users | /users, /users/new, /users/:username, /users/:username/edit | /api/users, /api/users/{username}, /api/users/{username}/me | UserService, UserRepository |
| cli_adapters | /settings | /api/cli-adapters, /api/cli-adapters/{cli_id} | CLIAdapterService, CLIAdapterRepository |
| tasks | /tasks | /api/tasks | TaskService, TaskRepository, TaskProcessor |
| system_settings | /settings | /api/settings | SystemSettingsService, SystemSettingsRepository |

## 4. 外部設計

### 4.1 画面一覧

| 画面 | パス | 権限 | 説明 |
| --- | --- | --- | --- |
| ログイン | /login | 未認証可 | JWTログインを行う |
| ユーザー一覧 | /users | admin | ユーザー検索と一覧表示を行う |
| ユーザー作成 | /users/new | admin | 新規ユーザーを作成する |
| ユーザー詳細 | /users/:username | admin または本人 | ユーザー詳細を表示する |
| ユーザー編集 | /users/:username/edit | admin または本人 | ユーザー情報を編集する |
| タスク一覧 | /tasks | 認証済み | タスク履歴を表示する |
| システム設定 | /settings | admin | F-3/F-4テンプレートとCLI設定を扱う |

### 4.2 画面遷移

```mermaid
graph TD
    Login[/login/] -->|admin| Users[/users/]
    Login -->|user| Tasks[/tasks/]
    Users --> UserDetail[/users/:username/]
    Users --> UserCreate[/users/new/]
    UserDetail --> UserEdit[/users/:username/edit/]
    Users --> Tasks
    Users --> Settings[/settings/]
    Settings --> Users
```

### 4.3 フロントエンドの認可制御

- 未認証で認証必須画面へ遷移した場合は /login へリダイレクトする
- 認証済みで /login に遷移した場合は admin は /users、一般ユーザーは /tasks にリダイレクトする
- 一般ユーザーが管理者専用画面へ遷移した場合は /tasks にリダイレクトする
- 一般ユーザーが他ユーザーの詳細画面または編集画面へ遷移した場合は /tasks にリダイレクトする

### 4.4 API一覧

| メソッド | パス | 権限 | 説明 |
| --- | --- | --- | --- |
| POST | /api/auth/login | 認証不要 | JWTトークンを発行する |
| GET | /api/users | admin | ユーザー一覧を取得する |
| POST | /api/users | admin | ユーザーを作成する |
| GET | /api/users/{username} | admin または本人 | ユーザー詳細を取得する |
| PUT | /api/users/{username} | admin | 管理者権限でユーザーを更新する（Virtual Key 保存時にLLMキー妥当性チェックを実施） |
| PUT | /api/users/{username}/me | 本人 | 一般ユーザーが自分を更新する |
| DELETE | /api/users/{username} | admin | ユーザーを削除する |
| GET | /api/users/{username}/model-candidates | admin または本人 | モデル候補一覧を取得する（LiteLLMから取得し、失敗時は空リストを返す） |
| GET | /api/tasks | 認証済み | タスク一覧を取得する |
| GET | /api/cli-adapters | admin | CLIアダプタ一覧を取得する |
| POST | /api/cli-adapters | admin | CLIアダプタを作成する |
| PUT | /api/cli-adapters/{cli_id} | admin | CLIアダプタを更新する |
| DELETE | /api/cli-adapters/{cli_id} | admin | CLIアダプタを削除する |
| GET | /api/settings | admin | システム設定を取得する |
| PUT | /api/settings | admin | システム設定を更新する |
| GET | /health | 認証不要 | backend ヘルスチェック |

### 4.5 外部システム連携

| 外部システム | 連携方法 | 目的 |
| --- | --- | --- |
| GitLab REST API | HTTPS REST API | Issue/MR取得、コメント投稿、ブランチ作成、MR作成 |
| GitLab Webhook | HTTP POST | Issue/MRイベント受信 |
| LiteLLM Proxy | HTTP API | CLI実行時のモデル呼び出し先 |

### 4.6 外部データベース連携

外部データベースとの直接連携は行わない。アプリケーションが利用する永続化先は PostgreSQL のみであり、外部DB連携設計は不要とする。

### 4.7 APIバリデーション・エラー仕様

| 区分 | 内容 |
| --- | --- |
| 共通入力検証 | FastAPI と Pydantic スキーマで型、必須項目、制約を検証する |
| 400 | ロール値不正、現在パスワード不足、組み込みCLI削除、参照中CLI削除などの業務エラー |
| 401 | ログイン失敗、JWT不正、JWT期限切れ |
| 403 | admin 権限不足、本人以外の参照更新 |
| 404 | 対象ユーザー、CLIアダプタ、タスク、GitLabリソース不在 |
| 409 | email 重複、cli_id 重複、タスク重複挿入 |
| 422 | リクエストボディやクエリのバリデーション不正 |

### 4.8 CUI引数・環境変数仕様

| コンポーネント | 起動方式 | 主な設定受け取り |
| --- | --- | --- |
| backend | コンテナ起動時に自動起動 | `DATABASE_URL`、`JWT_SECRET_KEY`（JWT有効期限は実装固定24時間） |
| producer | `python producer.py` | `RABBITMQ_URL`、`GITLAB_API_URL`、`GITLAB_WEBHOOK_SECRET`、`POLLING_INTERVAL_SECONDS` |
| consumer | `python consumer.py` | `RABBITMQ_URL`、`DATABASE_URL`、`CLI_EXEC_TIMEOUT_SEC`、`PROGRESS_REPORT_INTERVAL_SEC`、`PROGRESS_REPORT_SUMMARY_LINES` |
| setup系スクリプト | 手動実行 | `.env` のAPIキー、GitLab接続情報、LiteLLM接続情報 |

CLI実行コンテナへは、CLIアダプタ設定の `env_mappings` と `config_content_env` に基づき必要な環境変数を注入する。プロンプト本文は環境変数ではなく `/tmp/prompt.txt` を介して受け渡す。

cli-execコンテナは、以下の言語・フレームワークを標準でサポートする。

| 言語 / FW | 標準サポート内容 |
| --- | --- |
| Python | Python・`uv`パッケージマネージャ |
| Node.js / npm | Node.js・`npm` |
| Playwright | Playwright（ブラウザテスト実行環境含む） |

## 5. 内部設計

### 5.0 全機能ユーザー利用フロー

システム全体の利用の流れを俯瞰するため、管理者によるユーザー登録から Issue 処理、MR 処理完了までの主要フローを以下に示す。

```mermaid
flowchart TD
    A[管理者がユーザーを新規登録する] --> B[GitLabユーザー名・Virtual Key・デフォルトCLI・モデルを入力して作成]
    B --> C[GitLab開発者がIssueを作成する]
    C --> D[IssueにbotをアサインしてGitLabラベルを付与する]
    D --> E{Webhook受信 または ポーリング検出}
    E --> F[IssueからMR生成処理を開始する]
    F --> G[IssueのauthorのVirtual Keyを取得する]
    G --> G2[Issueに処理中ラベルを付与する]
    G2 --> H[cli-execコンテナを起動してCLIを実行し、ブランチ名・MRタイトルを生成する]
    H --> I[GitLab APIで作業ブランチとDraft MRを作成する]
    I --> I2[IssueのauthorをMRの最初のレビュアーに設定する]
    I2 --> I3[IssueのコメントをMRへコピーする]
    I3 --> J[IssueにMR作成完了コメントを投稿する]
    J --> J2[Issueはクローズしない]
    J2 --> K[次のWebhookまたはポーリングでMRを検出する]
    K --> L[MR処理を開始する]
    L --> M[最初のレビュアーのVirtual Keyを取得する]
    M --> M2[MRに処理中ラベルを付与する]
    M2 --> N[MR descriptionからCLI種別・モデルを決定する]
    N --> O[cli-execコンテナを起動し、MRブランチをcloneしてcheckoutする]
    O --> P[Virtual Keyを設定してCLIを起動する]
    P --> P2[MRに処理開始コメントを投稿する]
    P2 --> Q[CLIがdescriptionの指示に従いコード変更・テストを実行する]
    Q --> Q2[CLIの標準出力を定期的にMRへ進捗コメントとして投稿する]
    Q2 --> R[変更をコミット・プッシュする]
    R --> S[MRの処理中ラベルを削除し完了コメントを投稿しdoneラベルを付与する]
```

### 5.1 Webhook受信フロー

```mermaid
sequenceDiagram
    participant GL as GitLab Group Webhook
    participant WS as WebhookServer
    participant EH as GitLabEventHandler
    participant DB as PostgreSQL
    participant MQ as RabbitMQ

    GL->>WS: POST /webhook (X-Idempotency-Key ヘッダー付き)
    WS->>WS: X-Gitlab-Token と設定値を直接比較
    alt 検証失敗
        WS-->>GL: 403
    else ペイロード不正
        WS->>WS: WARNINGログを記録する
        WS-->>GL: 200（GitLab再送に委譲）
    else 検証成功
        WS->>EH: handle_event(payload, idempotency_key)
        EH->>EH: Idempotency-Key 重複チェック（メモリ内セット）
        alt 重複受信
            EH-->>WS: スキップ（DEBUG ログ）
            WS-->>GL: 200
        else 新規受信
            EH->>EH: botアサイン、botラベル、doneラベル不在を判定
            EH->>DB: pending/running 重複有無を確認
            EH->>DB: tasks に pending を挿入
            EH->>MQ: TaskMessage を publish
            WS-->>GL: 200
        end
    end
```

### 5.2 ポーリングフロー

- producer は polling_interval_seconds ごとに対象プロジェクトを巡回する
- Issue と Merge Request を GitLab API から取得する
- GitLabEventHandler に共通処理を集約し、Webhook経由と同じ投入判定を行う

### 5.3 F-3 Issue から MR 生成

- 対象ユーザーを users から取得する
- 無効ユーザーまたは未登録ユーザーの場合は Issue にエラーコメントを投稿して tasks を failed にする
- system_settings と users の設定をマージして MCP 設定文字列を構築する
- default_cli と default_model を使って CLI アダプタを解決する
- CLI コンテナを起動し、/tmp/prompt.txt にプロンプトを書き込む
- CLI標準出力の最終行JSONから branch_name と mr_title を取得する
- GitLab にブランチを作成し、Draft MR を作成する
- Issueコメントを MR にコピーし、Issue 側に完了コメントを投稿する
- タスクを completed に更新する

### 5.4 F-4 MR 処理

- 最初の reviewer を優先し、未設定時は author を処理ユーザーとする
- MR description から agent: 行を解析し、CLI と model の上書きを行う
- CLI コンテナを起動し、GitLab PAT を埋め込んだ clone URL でリポジトリを取得する
- コンテナ起動直後に `git config --global user.name` および `user.email` を `GITLAB_BOT_NAME@localhost` で設定する
- EBPFEnvironmentChecker で BTF 存在・ケーパビリティを確認して eBPF 利用可否を判定する
  - 利用可能な場合は TTYWaitDetector（Tracee コンテナ）を起動して CLI の TTY read 待機を監視する
  - 利用不可の場合は WARNING を記録して TTY 検知なしで継続する
- CLI が TTY 待機状態を検知した場合は CLI を強制終了し、失敗コメントを GitLab へ投稿して tasks を failed にする（error_message と cli_log に検知情報を記録）
- ProgressManager が一定間隔で1件の MR コメントを作成または更新する
- monitor_assignees が一定間隔で bot のアサイン解除を監視する
- 正常終了時はラベル更新、完了コメント投稿、tasks completed を行う
- 失敗時はエラーコメント投稿、tasks failed を行う

### 5.5 トランザクション境界

| 処理 | 境界 | 備考 |
| --- | --- | --- |
| タスク投入 | tasks insert 単位 | 部分ユニーク制約で重複を防ぐ |
| ユーザー作成・更新・削除 | 1API呼び出し単位 | Repository 経由で commit する |
| タスク状態更新 | 1更新単位 | running、completed、failed を都度反映する |
| システム設定更新 | 1API呼び出し単位 | 指定されたキーのみ更新する |

### 5.6 排他制御

| 対象 | 方式 | 内容 |
| --- | --- | --- |
| タスク重複 | DB制約 | tasks_no_duplicate_active により pending/running の重複を防ぐ |
| email 重複 | DB制約 | users.email の UNIQUE 制約 |
| cli_id 重複 | PK制約 | cli_adapters.cli_id の主キー制約 |

### 5.7 状態遷移

#### tasks の状態遷移

```mermaid
stateDiagram-v2
    [*] --> pending
    pending --> running
    running --> completed
    running --> failed
```

#### users の状態管理

```mermaid
stateDiagram-v2
    [*] --> active : 管理者がユーザー作成
    active --> inactive : 管理者が無効化
    inactive --> active : 管理者が有効化
    active --> [*] : 管理者がユーザー削除
    inactive --> [*] : 管理者がユーザー削除
```

cli_adapters と system_settings は業務ワークフロー上の状態遷移を持たない。

#### cli_adapters のライフサイクルルール

cli_adapters にはステータス管理はないが、以下のライフサイクルルールが適用される。

| 操作 | 内容 |
| --- | --- |
| 初期データ投入 | システム初期化時に組み込みアダプタ（`claude`・`opencode`）が自動登録される |
| 管理者による追加 | システム設定画面にて新規CLIアダプタを登録できる |
| 管理者による編集 | システム設定画面にて既存アダプタの各属性を変更できる |
| 管理者による削除 | `is_builtin = false` のアダプタのみ削除可能。削除時にそのCLIエージェントIDを `default_cli` に持つユーザーが存在する場合はエラーを返し削除を拒否する |

## 6. クラス・モジュール設計

### 6.1 主要クラス一覧

| 配置 | クラスまたは実体 | 役割 |
| --- | --- | --- |
| shared/config/config.py | Settings | 環境変数設定を保持する |
| shared/gitlab_client/gitlab_client.py | GitLabClient | GitLab API 操作を担当する |
| shared/messaging/rabbitmq_client.py | RabbitMQClient | RabbitMQ publish/consume を担当する |
| shared/models/db.py | User, Task, CLIAdapter, SystemSetting | ORMモデルを表す |
| producer/gitlab_event_handler.py | GitLabEventHandler | イベント判定とタスク投入を担当する |
| producer/gitlab_event_handler.py | DuplicateCheckService | タスク重複を確認する |
| producer/webhook_server.py | WebhookServer | Webhook受信とトークン検証を担当する |
| producer/polling_loop.py | PollingLoop | GitLabポーリングを担当する |
| producer/producer.py | main | Producer全体起動を担当する |
| consumer/consumer.py | ConsumerWorker | RabbitMQのデキューとディスパッチを担当する |
| consumer/task_processor.py | TaskProcessor | task_type に応じて処理を振り分ける |
| consumer/issue_to_mr_converter.py | IssueToMRConverter | F-3処理を担当する |
| consumer/mr_processor.py | MRProcessor | F-4処理を担当する |
| consumer/cli_container_manager.py | CLIContainerManager | CLIコンテナ操作・git config設定を担当する |
| consumer/ebpf_environment_checker.py | EBPFEnvironmentChecker | BTF存在・ケーパビリティを確認してeBPF利用可否を判定する |
| consumer/tty_wait_detector.py | TTYWaitDetector | Traceeコンテナを起動してCLIのTTY待機を検知する |
| consumer/cli_adapter_resolver.py | CLIAdapterResolver | CLI起動情報を解決する |
| consumer/progress_manager.py | ProgressManager | 進捗コメント更新を担当する |
| consumer/prompt_builder.py | PromptBuilder | F-3/F-4プロンプトを構築する |
| consumer/virtual_key_service.py | VirtualKeyService | Virtual Key の暗号化と復号を担当する |
| consumer/cli_log_masker.py | CLILogMasker | ログ中の機密値マスクを担当する |
| backend/services/auth_service.py | AuthService | JWT とパスワード認証を担当する |
| backend/services/user_service.py | UserService | ユーザー業務ロジック・LLMキー保存時バリデーションを担当する |
| backend/services/model_candidate_service.py | ModelCandidateService | LiteLLMキー検証・モデル候補取得を担当する |
| backend/services/task_service.py | TaskService | タスク一覧取得を担当する |
| backend/services/cli_adapter_service.py | CLIAdapterService | CLIアダプタ管理を担当する |
| backend/services/system_settings_service.py | SystemSettingsService | システム設定管理を担当する |
| backend/repositories/*.py | 各Repository | 永続化操作を担当する |
| backend/routers/*.py | router | APIエンドポイント定義を担当する |

### 6.2 モジュール関係図

```mermaid
classDiagram
    class GitLabClient
    class RabbitMQClient
    class Settings
    class GitLabEventHandler
    class DuplicateCheckService
    class WebhookServer
    class PollingLoop
    class ConsumerWorker
    class TaskProcessor
    class IssueToMRConverter
    class MRProcessor
    class CLIContainerManager
    class CLIAdapterResolver
    class ProgressManager
    class PromptBuilder
    class VirtualKeyService
    class CLILogMasker
    class AuthService
    class UserService
    class TaskService
    class CLIAdapterService
    class SystemSettingsService

    WebhookServer --> GitLabEventHandler
    PollingLoop --> GitLabEventHandler
    GitLabEventHandler --> DuplicateCheckService
    GitLabEventHandler --> RabbitMQClient
    GitLabEventHandler --> GitLabClient
    ConsumerWorker --> TaskProcessor
    TaskProcessor --> IssueToMRConverter
    TaskProcessor --> MRProcessor
    IssueToMRConverter --> CLIContainerManager
    IssueToMRConverter --> CLIAdapterResolver
    IssueToMRConverter --> PromptBuilder
    IssueToMRConverter --> VirtualKeyService
    IssueToMRConverter --> GitLabClient
    MRProcessor --> CLIContainerManager
    MRProcessor --> CLIAdapterResolver
    MRProcessor --> ProgressManager
    MRProcessor --> PromptBuilder
    MRProcessor --> VirtualKeyService
    MRProcessor --> GitLabClient
```

## 7. ソースコード構成

### 7.1 ディレクトリ構成

```text
CodingAgentAutomata/
├── .env.example
├── docker-compose.yml
├── backend/
│   ├── alembic/
│   ├── repositories/
│   ├── routers/
│   ├── schemas/
│   ├── services/
│   ├── Dockerfile
│   ├── main.py
│   └── pyproject.toml
├── consumer/
│   ├── Dockerfile
│   ├── consumer.py
│   ├── task_processor.py
│   ├── issue_to_mr_converter.py
│   ├── mr_processor.py
│   ├── cli_container_manager.py
│   ├── cli_adapter_resolver.py
│   ├── progress_manager.py
│   ├── prompt_builder.py
│   ├── cli_log_masker.py
│   ├── virtual_key_service.py
│   └── pyproject.toml
├── producer/
│   ├── Dockerfile
│   ├── producer.py
│   ├── webhook_server.py
│   ├── polling_loop.py
│   ├── gitlab_event_handler.py
│   └── pyproject.toml
├── shared/
│   ├── config/
│   ├── database/
│   ├── gitlab_client/
│   ├── messaging/
│   └── models/
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── plugins/
│   │   ├── router/
│   │   ├── stores/
│   │   ├── views/
│   │   ├── App.vue
│   │   └── main.ts
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── package.json
│   └── vite.config.ts
├── e2e/
│   ├── tests/
│   ├── global-setup.ts
│   ├── package.json
│   └── playwright.config.ts
├── scripts/
│   ├── setup.py
│   ├── setup.sh
│   ├── test_setup.py
│   ├── test_setup.sh
│   └── gitlab_setup.py
└── cli-exec/
    ├── claude/
    └── opencode/
```

### 7.2 完全ファイル対応表

#### Backend インフラストラクチャ

| ファイル | 役割 |
| --- | --- |
| backend/main.py | FastAPI起動、Alembic自動実行、全ルーター登録、CORS設定、ヘルスチェック |
| backend/Dockerfile | Python 3.12 ベースイメージ、FastAPI コンテナ構築、shared モジュールインストール |
| backend/pyproject.toml | FastAPI、SQLAlchemy、Alembic、Pydantic 等の依存パッケージ定義 |
| backend/alembic.ini | Alembic マイグレーションツール設定ファイル |
| backend/alembic/env.py | Alembic 環境設定、オートマイグレーション有効化、DATABASE_URL 環境変数対応 |
| backend/alembic/versions/__init__.py | マイグレーション版管理用 Python パッケージ初期化 |
| backend/alembic/versions/001_initial.py | 初期テーブル作成マイグレーション（users、cli_adapters、tasks、system_settings） |

✅ **04/24チェック完了**

#### Backend スキーマ定義

| ファイル | 役割 |
| --- | --- |
| backend/schemas/__init__.py | スキーマ モジュール初期化 |
| backend/schemas/auth.py | ログインリクエスト、JWT トークンレスポンス Pydantic スキーマ |
| backend/schemas/user.py | ユーザーCRUD用リクエスト・レスポンス Pydantic スキーマ |
| backend/schemas/task.py | タスク一覧取得用リスポンス Pydantic スキーマ |
| backend/schemas/cli_adapter.py | CLIアダプタCRUD用リクエスト・レスポンス Pydantic スキーマ |
| backend/schemas/settings.py | システム設定取得・更新用リクエスト・レスポンス Pydantic スキーマ |

✅ **04/24チェック完了**

#### Backend ルーター

| ファイル | 役割 |
| --- | --- |
| backend/routers/__init__.py | ルーター モジュール初期化 |
| backend/routers/auth.py | POST /api/auth/login ログインエンドポイント |
| backend/routers/users.py | GET/POST/PUT/DELETE /api/users ユーザーAPI |
| backend/routers/tasks.py | GET /api/tasks タスク一覧取得API |
| backend/routers/cli_adapters.py | GET/POST/PUT/DELETE /api/cli-adapters CLIアダプタAPI |
| backend/routers/settings.py | GET/PUT /api/settings システム設定API |

✅ **04/24チェック完了**

#### Backend リポジトリ

| ファイル | 役割 |
| --- | --- |
| backend/repositories/__init__.py | リポジトリ モジュール初期化 |
| backend/repositories/user_repository.py | users テーブルのデータアクセス（取得・作成・更新・削除・重複チェック） |
| backend/repositories/task_repository.py | tasks テーブルのデータアクセス（フィルタリング・ページネーション） |
| backend/repositories/cli_adapter_repository.py | cli_adapters テーブルのデータアクセス（CRUD・参照チェック） |
| backend/repositories/system_settings_repository.py | system_settings テーブルのデータアクセス（キーバリュー操作） |

✅ **04/24チェック完了**

#### Backend サービス

| ファイル | 役割 |
| --- | --- |
| backend/services/__init__.py | サービス モジュール初期化 |
| backend/services/auth_service.py | JWT トークン発行・検証、パスワード認証（bcrypt ハッシュ）、ログイン処理 |
| backend/services/user_service.py | ユーザーCRUD、Virtual Key 暗号化・復号、パスワードハッシュ化 |
| backend/services/task_service.py | タスク一覧取得（admin は全体、一般ユーザーは自分のみ）、フィルタ処理 |
| backend/services/cli_adapter_service.py | CLIアダプタCRUD、組み込みアダプタ保護、ユーザー参照チェック |
| backend/services/system_settings_service.py | システム設定（プロンプトテンプレート・MCP設定）の取得・更新 |
| backend/services/virtual_key_service.py | Virtual Key の AES-256-GCM 暗号化・復号化 |

✅ **04/24チェック完了**

#### Producer コンポーネント

| ファイル | 役割 |
| --- | --- |
| producer/producer.py | Producer エントリーポイント、WebhookServer と PollingLoop を asyncio.gather で並行起動 |
| producer/webhook_server.py | aiohttp を使用した Webhook 受信サーバー、X-Gitlab-Token トークン検証 |
| producer/polling_loop.py | POLLING_INTERVAL_SECONDS ごとに GitLab API を問い合わせ、Issue/MR 取得 |
| producer/gitlab_event_handler.py | イベント解析、条件判定、タスク RabbitMQ 投入、重複チェック |
| producer/pyproject.toml | Producer の依存パッケージ定義（aiohttp、python-gitlab、pika） |
| producer/Dockerfile | Python 3.12 ベースイメージ、Producer コンテナ構築 |

✅ **04/24チェック完了**

#### Consumer コンポーネント

| ファイル | 役割 |
| --- | --- |
| consumer/consumer.py | Consumer エントリーポイント・ConsumerWorker、RabbitMQ デキューとディスパッチ、グレースフルシャットダウン |
| consumer/task_processor.py | タスク種別ディスパッチャー、task_type に応じて F-3/F-4 処理に振り分け |
| consumer/issue_to_mr_converter.py | F-3 実装、Issue に対する CLI 実行、Draft MR 作成 |
| consumer/mr_processor.py | F-4 実装、MR に対する CLI 実行、進捗報告、アサイニー監視 |
| consumer/cli_container_manager.py | Docker API 経由の CLI コンテナ起動・停止、docker.sock マウント対応 |
| consumer/cli_adapter_resolver.py | CLI 起動情報解決、環境変数・コマンドテンプレート組立 |
| consumer/progress_manager.py | GitLab API 経由の進捗コメント追加 |
| consumer/prompt_builder.py | F-3/F-4 プロンプト構築、ユーザーテンプレート・システムMCP設定反映 |
| consumer/cli_log_masker.py | CLI ログ内の Virtual Key・GitLab PAT をマスク処理 |
| consumer/virtual_key_service.py | Virtual Key の AES-256-GCM 復号化（consumer用） |
| consumer/pyproject.toml | Consumer の依存パッケージ定義（pika、docker、python-gitlab） |
| consumer/Dockerfile | Python 3.12 ベースイメージ、Consumer コンテナ構築、docker.sock マウント対応 |

✅ **04/24チェック完了**

#### Shared 共通モジュール

| ファイル | 役割 |
| --- | --- |
| shared/config/config.py | pydantic-settings 環境変数設定管理（DATABASE_URL、GITLAB_API_URL 等） |
| shared/database/database.py | SQLAlchemy Engine・Session・Base 管理、DB 接続実装 |
| shared/gitlab_client/gitlab_client.py | GitLab REST API ラッパー、エラーハンドリング、リトライ実装 |
| shared/messaging/rabbitmq_client.py | RabbitMQ 接続・publish/consume 実装、リトライ対応 |
| shared/models/db.py | SQLAlchemy ORM モデル定義（User、Task、CLIAdapter、SystemSetting） |
| shared/models/gitlab.py | GitLab REST API レスポンス用 Pydantic スキーマ |
| shared/models/task.py | RabbitMQ タスクメッセージ用 Pydantic スキーマ |
| shared/pyproject.toml | Shared の依存パッケージ定義（SQLAlchemy、pydantic、python-gitlab、pika） |

✅ **04/24チェック完了**

#### Frontend フロントエンド

| ファイル | 役割 |
| --- | --- |
| frontend/src/main.ts | Vue app インスタンス作成、Pinia・router・vuetify プラグイン登録 |
| frontend/src/App.vue | ルートコンポーネント、ナビゲーションレイアウト |
| frontend/src/router/index.ts | Vue Router ルート定義、認証ガード（未認証リダイレクト、権限チェック） |
| frontend/src/api/client.ts | axios インスタンス設定、API 関数（login、getUsers、getTasks、createUser等） |
| frontend/src/stores/auth.ts | Pinia 認証ストア、ユーザー情報・トークン管理 |
| frontend/src/plugins/vuetify.ts | Vuetify テーマ・コンポーネント設定 |
| frontend/src/views/LoginView.vue | ログイン画面コンポーネント |
| frontend/src/views/TaskListView.vue | タスク一覧画面、フィルタ・ページネーション |
| frontend/src/views/UserListView.vue | ユーザー一覧画面、削除機能 |
| frontend/src/views/UserCreateView.vue | ユーザー作成画面 |
| frontend/src/views/UserEditView.vue | ユーザー編集画面（admin・本人のみ） |
| frontend/src/views/UserDetailView.vue | ユーザー詳細表示画面 |
| frontend/src/views/SettingsView.vue | システム設定画面（プロンプトテンプレート・CLIアダプタ設定） |
| frontend/Dockerfile | Node.js ベースイメージ、Vue ビルド、nginx 配信用コンテナ構築 |
| frontend/nginx.conf | nginx 設定ファイル、Vue SPA サポート、/api 逆プロキシ設定 |
| frontend/index.html | HTML エントリーポイント |
| frontend/vite.config.ts | Vite ビルド設定 |
| frontend/tsconfig.json | TypeScript 設定ファイル |
| frontend/tsconfig.node.json | TypeScript Node.js 設定 |
| frontend/package.json | フロントエンド依存パッケージ定義（Vue、Vuetify、Pinia、axios） |

✅ **04/24チェック完了**

#### E2E テスト

| ファイル | 役割 |
| --- | --- |
| e2e/global-setup.ts | Playwright グローバルセットアップ、テスト実行前の GitLab・RabbitMQ クリーンアップ |
| e2e/playwright.config.ts | Playwright 実行設定（baseURL、workers=1、タイムアウト） |
| e2e/tests/auth.spec.ts | 認証・認可テスト（ログイン、権限制御、ログアウト） |
| e2e/tests/users.spec.ts | ユーザー管理テスト（作成・編集・削除・重複エラー） |
| e2e/tests/tasks.spec.ts | タスク画面テスト（表示・フィルタ・ナビゲーション） |
| e2e/tests/gitlab_integration.spec.ts | GitLab 連携テスト（Webhook・ポーリング・MR処理・進捗更新） |
| e2e/package.json | E2E テスト依存パッケージ定義（@playwright/test） |

✅ **04/24チェック完了**

#### セットアップ・スクリプト

| ファイル | 役割 |
| --- | --- |
| scripts/setup.py | システム初期化スクリプト、管理者ユーザー作成・プロンプトテンプレート DB 投入 |
| scripts/setup.sh | setup.py 実行ラッパーシェルスクリプト |
| scripts/test_setup.py | テスト環境セットアップ、GitLab テストユーザー・プロジェクト・Webhook 設定 |
| scripts/test_setup.sh | test_setup.py 実行ラッパーシェルスクリプト |
| scripts/gitlab_setup.py | GitLab CE セットアップスクリプト、グループ・プロジェクト・ユーザー初期化 |

✅ **04/24チェック完了**

#### CLI 実行環境・モックサービス

| ファイル | 役割 |
| --- | --- |
| cli-exec/claude/Dockerfile | Claude CLI イメージビルド用 Dockerfile |
| cli-exec/opencode/Dockerfile | OpenCode CLI イメージビルド用 Dockerfile |
| mock-llm/server.py | モック LLM HTTP サーバー実装、Claude API 互換レスポンス |
| mock-llm/Dockerfile | Python モック LLM コンテナ構築 |

✅ **04/24チェック完了**

#### LiteLLM 設定

| ファイル | 役割 |
| --- | --- |
| litellm/config.yml | LiteLLM プロキシ設定（モック LLM バックエンド） |
| litellm/config-real.yml | LiteLLM プロキシ設定（実 LLM バックエンド、test-real プロファイル用） |

✅ **04/24チェック完了**

## 8. テスト設計

### 8.1 現在リポジトリに存在するテスト

| 種別 | 配置 | 内容 |
| --- | --- | --- |
| E2E | e2e/tests/auth.spec.ts | ログイン、認可、ログアウト |
| E2E | e2e/tests/users.spec.ts | ユーザー作成、編集、削除、重複エラー |
| E2E | e2e/tests/tasks.spec.ts | タスク画面表示、フィルタ、ナビゲーション |
| E2E | e2e/tests/gitlab_integration.spec.ts | Webhook、ポーリング、MR処理、進捗更新、重複防止 |

### 8.2 E2E実行方式

- Playwright は docker compose 上の test_playwright または test_playwright_real で実行する
- ベースURLは frontend サービス名を使う
- GitLab 統合テストは GitLab CE と LiteLLM 系サービスを含むプロファイル起動が前提である
- Playwright は workers を 1 に固定し、Consumer の単一処理前提に合わせる

### 8.3 テスト設計上の現状

- リポジトリには Python 側の単体テストおよび結合テストは配置されていない
- 現在の自動検証の中心は Playwright E2E である
- GitLab 統合テストはタスク状態を backend API から取得して補助判定する

## 9. 運用設計

### 9.1 起動プロファイル

| プロファイル | 用途 |
| --- | --- |
| 通常起動 | frontend、backend、producer、consumer、postgresql、rabbitmq を起動する |
| test | GitLab CE、mock_llm、litellm、test_playwright を追加する |
| test-real | GitLab CE、litellm_real、test_playwright_real を追加する |
| build-only | cli-exec 向けイメージだけをビルドする |

### 9.2 初期化とセットアップ

- backend は起動時に Alembic の head まで自動適用する
- scripts/setup.sh と scripts/setup.py は通常環境の初期設定を担当する
- scripts/test_setup.sh と scripts/test_setup.py は GitLab テスト環境とテストユーザー準備を担当する
- README.md に起動方法、環境変数、E2Eテスト実行方法を記載する

## 10. ログ・セキュリティ・監視

### 10.1 セキュリティ設計

| 項目 | 内容 |
| --- | --- |
| Virtual Key保存 | AES-256-GCM で暗号化して users.virtual_key_encrypted に保存する |
| パスワード保存 | bcrypt ハッシュで保存する |
| API認証 | JWT Bearer 認証を使用する |
| API認可 | admin 権限判定と本人判定を使い分ける |
| Webhook検証 | X-Gitlab-Token と設定値を直接比較する |
| CLIログ保護 | CLILogMasker で PAT 等をマスクして保存する |
| CLI秘密情報 | Virtual Key と GitLab PAT は実行時のみ使用し、コンテナ破棄で消去する |

### 10.2 ログ設計

| ログ対象 | 出力先 | 説明 |
| --- | --- | --- |
| アプリケーションログ | 各コンテナ標準出力 | producer、consumer、backend の動作ログ |
| CLI実行ログ | tasks.cli_log | Issue/MR 処理時のCLI出力 |
| エラー情報 | tasks.error_message および標準出力 | タスク失敗理由 |

### 10.2.1 監査ログ

認証・認可に紐づく専用の監査ログは、現行実装には存在しない。ユーザー更新や設定更新の履歴保持は未実装であり、必要になった場合は別途追加実装が必要である。

### 10.3 監視設計

| 対象 | 方法 | 備考 |
| --- | --- | --- |
| backend | /health | FastAPI 健康確認 |
| producer | /health | WebhookServer 健康確認 |
| 各コンテナ | restart: always | compose の自動再起動に依存 |
| postgresql | healthcheck | pg_isready を使用 |
| rabbitmq | コンテナ死活監視 | 管理UIの疎通確認は別運用 |

専用のアラート基盤や永続監視基盤は、このリポジトリ内には実装されていない。

## 11. E2Eシナリオ対応表

### 11.1 現在実装に対応するシナリオ

| シナリオID | 対応テスト | 検証内容 |
| --- | --- | --- |
| TS-01 | e2e/tests/auth.spec.ts | ログイン、未認証時遷移、権限制御によるリダイレクト |
| TS-02 | e2e/tests/users.spec.ts | ユーザー作成・編集・削除、重複時エラー |
| TS-03 | e2e/tests/tasks.spec.ts | タスク一覧表示、フィルタ、画面遷移 |
| TS-04 | e2e/tests/gitlab_integration.spec.ts | Webhook/ポーリング検出、MR処理、進捗更新、重複防止 |
| TS-5.1〜TS-5.10 | e2e/tests/tty_detection.spec.ts | TTY待機検知、eBPF環境判定、git config設定、タスク失敗報告 |
| TS-A-1〜TS-A-6 | e2e/tests/prompt_templates.spec.ts | プロンプトテンプレート必須指示反映 |
| TS-WB-1〜TS-WB-5 | e2e/tests/group_webhook.spec.ts | Group Webhook受信、Idempotency-Key重複抑止、WARNINGログ |
| TS-C-1〜TS-C-4 | e2e/tests/llm_settings.spec.ts | LLMキー保存時バリデーション、モデルサジェスト表示 |

### 11.2 運用上の補足

- Playwright 実行は docker compose の `test` または `test-real` プロファイルを使用する
- 現在の自動検証は E2E が中心であり、Python 単体テスト・結合テストは不要とする
