# GitLab自律コーディングエージェントシステム 実装タスク一覧

設計書: `docs/detail_design.md`

---

## フェーズ1: 基盤整備

### T1-1: プロジェクト構成・依存関係設定
- `docker-compose.yml` の作成（producer, consumer, backend, frontend, postgresql, rabbitmq サービス定義）
- `.env.example` の作成（全環境変数一覧・説明）
- 各コンポーネントの `pyproject.toml` / `package.json` 作成
- **完了条件**: `docker compose up` でサービスが全て起動する（アプリ未実装でも起動エラーがないこと）
- **バリデーション**: `docker compose ps` で全サービスが running 状態であること

### T1-2: sharedモジュール配置（AutomataCodex再利用）
- `shared/gitlab_client/gitlab_client.py` を AutomataCodex から取得・配置
- `shared/messaging/rabbitmq_client.py` を AutomataCodex から取得・配置
- `shared/database/database.py` を AutomataCodex から取得または新規作成（SQLAlchemy セッション管理）
- `shared/config/config.py` を AutomataCodex から取得・配置
- `shared/models/db.py`: SQLAlchemy ORMモデル（User, Task, CLIAdapter, SystemSetting）
- `shared/models/gitlab.py`: GitLabレスポンスPydanticモデル
- `shared/models/task.py`: タスクメッセージPydanticモデル
- **完了条件**: `python -c "from shared.gitlab_client.gitlab_client import GitLabClient"` がエラーなく実行できること
- **バリデーション**: 各モジュールのimportテストをpytestで実施

### T1-3: DBマイグレーション設定（Alembic）
- Alembic 初期化（`backend/alembic/`）
- 初期マイグレーションスクリプト作成（users, tasks, cli_adapters, system_settings テーブル）
- tasksテーブルの部分ユニーク制約（F-10重複防止）の追加
- backendコンテナ起動時にAlembic自動実行する設定
- **完了条件**: `docker compose up` 後に全テーブルがPostgreSQLに作成される
- **バリデーション**: `docker compose exec postgresql psql -U user -d db -c "\dt"` で4テーブルが確認できること

---

## フェーズ2: Backendの実装

### T2-1: 認証API（AuthRouter, AuthService）
- POST `/api/auth/login`（JWTトークン発行）
- bcryptパスワード照合ロジック（AuthService）
- JWT発行（HS256、有効期限24時間）
- JWT検証ミドルウェア（FastAPI依存性注入）
- **完了条件**: POST `/api/auth/login` でJWTトークンが返却される
- **バリデーション**: 正しいパスワード・誤ったパスワードで結合テスト実施

### T2-2: ユーザーCRUD API（UserRouter, UserService, UserRepository）
- GET `/api/users`（admin限定・検索対応）
- POST `/api/users`（admin限定・メール重複チェック・AES-256-GCMでVirtual Key暗号化保存）
- GET `/api/users/{username}`（admin: 全員 / user: 自分のみ）
- PUT `/api/users/{username}`（admin: 全項目 / user: 制限項目のみ）
- DELETE `/api/users/{username}`（admin限定）
- VirtualKeyService（AES-256-GCM暗号化・復号）をbackend/でも使用
- **完了条件**: 全CRUDエンドポイントが正常動作し、権限チェックが機能する
- **バリデーション**: admin・user それぞれのロールで各エンドポイントへのアクセス結合テスト

### T2-3: タスク履歴 API（TaskRouter, TaskService, TaskRepository）
- GET `/api/tasks`（admin: 全タスク / user: 自分のみ・ユーザー名/ステータス/種別フィルタ対応）
- **完了条件**: フィルタ付きでタスク一覧が返却される
- **バリデーション**: admin・user ロールで結合テスト実施

### T2-4: CLIアダプタ CRUD API（CLIAdapterRouter, CLIAdapterService, CLIAdapterRepository）
- GET `/api/cli-adapters`
- POST `/api/cli-adapters`
- PUT `/api/cli-adapters/{cli_id}`
- DELETE `/api/cli-adapters/{cli_id}`（is_builtin=trueは拒否・default_cli参照中は拒否）
- **完了条件**: 全CRUDが動作し、組み込みアダプタ削除・参照中アダプタ削除が正しく拒否される
- **バリデーション**: 異常系（組み込み削除・参照中削除）の結合テスト実施

### T2-5: システム設定 API（SystemSettingsRouter, SystemSettingsService, SystemSettingsRepository）
- GET `/api/settings`
- PUT `/api/settings`
- **完了条件**: 設定取得・更新が動作する
- **バリデーション**: admin・user ロールで結合テスト実施

### T2-6: Pydanticスキーマ・バリデーション
- `backend/schemas/` 以下の全スキーマ定義（user.py, task.py, cli_adapter.py, settings.py）
- 各エンドポイントの入力バリデーション（必須フィールド・型・フォーマット）
- **完了条件**: 不正なリクエストボディで422が返却される
- **バリデーション**: 各スキーマの単体テスト実施

---

## フェーズ3: Frontendの実装

### T3-1: フロントエンド基盤（Vue + Vuetify + Vue Router + Pinia）
- `frontend/Dockerfile`（マルチステージビルド: npm build → nginx）
- `frontend/nginx.conf`（`/api/` リバースプロキシ設定）
- Vue Router設定（SC-01〜SC-07ルーティング）
- Piniaストア（認証状態・JWTトークン管理）
- axiosラッパー（`/api/` ベースURL・認証ヘッダー自動付与）
- 未認証時のリダイレクト（ナビゲーションガード）
- **完了条件**: `docker compose up` 後にブラウザで `http://localhost:80` にアクセスしログイン画面が表示される
- **バリデーション**: ブラウザで画面表示を確認

### T3-2: SC-01 ログイン画面
- ユーザー名・パスワード入力フォーム
- POST `/api/auth/login` API呼び出し・JWT保存
- ログイン成功後ロールに応じたリダイレクト（admin: SC-02 / user: SC-06）
- **完了条件**: ログインできJWTが保存される
- **バリデーション**: 正しい認証・誤った認証でのE2Eテスト実施

### T3-3: SC-02 ユーザー一覧（admin）
- ユーザー一覧テーブル（ユーザー名・メール・ロール・ステータス）
- ユーザー名検索ボックス
- 新規作成ボタン（SC-04へ）
- ユーザー名クリックでSC-03へ
- **完了条件**: ユーザー一覧が表示される
- **バリデーション**: E2Eテスト実施

### T3-4: SC-03 ユーザー詳細
- ユーザー情報表示
- 編集ボタン（SC-05へ）
- 削除ボタン（adminのみ表示・確認ダイアログ）
- **完了条件**: ユーザー詳細が表示される
- **バリデーション**: E2Eテスト実施

### T3-5: SC-04 ユーザー作成（admin）
- 新規ユーザー入力フォーム（全項目）
- POST `/api/users` API呼び出し
- バリデーションエラー表示
- **完了条件**: ユーザーを作成できる
- **バリデーション**: E2Eテスト実施（正常・重複メールアドレス）

### T3-6: SC-05 ユーザー編集
- 編集フォーム（ロールに応じた表示フィールド切り替え）
- F-4テンプレート「クリア」ボタン
- PUT `/api/users/{username}` API呼び出し
- **完了条件**: 編集できる（admin・user でフィールドが切り替わる）
- **バリデーション**: E2Eテスト実施

### T3-7: SC-06 タスク実行履歴
- タスク一覧テーブル（タスクUUID・ユーザー名・種別・ステータス・CLI・モデル・日時）
- フィルタ（ユーザー名・ステータス・種別）
- user ロールではユーザー名フィルタが自分のみ固定
- **完了条件**: タスク履歴が表示される
- **バリデーション**: E2Eテスト実施

### T3-8: SC-07 システム設定（admin）
- F-3/F-4プロンプトテンプレート編集
- システムMCP設定編集
- CLIアダプタ一覧・追加・編集・削除
- **完了条件**: 設定の確認・更新ができる
- **バリデーション**: E2Eテスト実施

---

## フェーズ4: Producerの実装

### T4-1: WebhookServerの実装
- `producer/webhook_server.py`（FastAPI/AioHTTPでHTTP待受）
- HMAC-SHA256署名検証（GITLAB_WEBHOOK_SECRET）
- `/health` エンドポイント
- **完了条件**: WebhookリクエストをHMAC検証して受理/拒否できる
- **バリデーション**: 単体テスト実施（正当・不正HMAC）

### T4-2: GitLabEventHandlerの実装
- `producer/gitlab_event_handler.py`
- botアサイン＋特定ラベルの判定ロジック
- DuplicateCheckService（tasks テーブルのpending/running確認）
- タスクメッセージをRabbitMQに投入・DBにpendingレコード挿入
- **完了条件**: 条件に一致するIssue/MRのみタスク投入される
- **バリデーション**: 単体テスト実施（条件一致・不一致・重複チェック）

### T4-3: PollingLoopの実装
- `producer/polling_loop.py`
- POLLING_INTERVAL_SECONDS 秒ごとにGitLab APIを問い合わせ
- GitLabEventHandlerに委譲
- **完了条件**: 指定間隔でポーリングが動作する
- **バリデーション**: モック環境での単体テスト実施

### T4-4: Producerエントリーポイント
- `producer/producer.py`（WebhookServer＋PollingLoop を並行起動）
- **完了条件**: WebhookとポーリングがDockerコンテナ内で同時動作する
- **バリデーション**: docker-compose 起動後にWebhookエンドポイントが応答すること

---

## フェーズ5: Consumerの実装

### T5-1: VirtualKeyService・CLILogMaskerの実装
- `consumer/virtual_key_service.py`（AES-256-GCM暗号化・復号）
- `consumer/cli_log_masker.py`（PATパターンのマスク）
- **完了条件**: 暗号化→復号が元の値と一致する。PATパターンがマスクされる
- **バリデーション**: 単体テスト実施

### T5-2: CLIAdapterResolver・PromptBuilderの実装
- `consumer/cli_adapter_resolver.py`
- `consumer/prompt_builder.py`（F-3/F-4テンプレート変数展開・ユーザー個別テンプレート優先ロジック）
- **完了条件**: claudeとopencode それぞれの環境変数・起動コマンドが正しく構築される
- **バリデーション**: 単体テスト実施（claude・opencode・ユーザー個別テンプレート）

### T5-3: CLIContainerManagerの実装
- `consumer/cli_container_manager.py`（Docker SDK使用）
- コンテナ起動（start_container）
- コンテナ内コマンド実行（exec_command）: F-4のgit clone・チェックアウト・git push
- CLIプロセスのみ強制終了（kill_process）
- コンテナ破棄（stop_container）
- 標準出力ストリーム取得（get_stdout_stream）
- コンテナ名フォーマット: `cli-exec-{cli_id}-{task_uuid}`
- **完了条件**: Docker APIでコンテナを起動・実行・破棄できる
- **バリデーション**: Docker デーモンアクセスありの結合テスト実施

### T5-4: ProgressManagerの実装
- `consumer/progress_manager.py`
- 非同期タスクでCLI標準出力バッファを定期読み取り
- PROGRESS_REPORT_BUFFER_MAX_LINES行超時に古い行を破棄
- `<details>` 形式のMRコメント作成/更新（GitLabClient.create_merge_request_note / update_merge_request_note）
- **完了条件**: PROGRESS_REPORT_INTERVAL_SEC 秒ごとにGitLabコメントが更新される
- **バリデーション**: 単体テスト実施（バッファ上限・更新間隔）

### T5-5: IssueToMRConverterの実装（F-3）
- `consumer/issue_to_mr_converter.py`
- Virtual Key取得・復号（未登録・無効ユーザーチェック）
- Issueに処理中ラベル付与
- プロンプト生成（PromptBuilder）
- CLIコンテナ起動（CLIContainerManager）・CLIの標準出力最終行のJSONパース（branch_name, mr_title取得）
- ブランチ作成・Draft MR作成（IssueのdescriptionをMR descriptionに設定）
- IssueのauthorをMRの最初のレビュアーに設定
- IssueのコメントをすべてMRにコピー
- IssueにMR作成完了コメント投稿・doneラベル付与・処理中ラベル削除
- コンテナ即時破棄
- **完了条件**: F-3フロー全体が動作する（GitLab上にブランチとDraft MRが作成される）
- **バリデーション**: テスト環境でE2E動作確認（T-04/T-05）

### T5-6: MRProcessorの実装（F-4）
- `consumer/mr_processor.py`
- Virtual Key取得（最初のレビュアー → なければauthor）
- MRに処理中ラベル付与
- MR descriptionの `agent:` 行解析（CLI/モデル上書き）
- プロンプト生成（PromptBuilder）
- CLIコンテナ起動（PAT埋め込みURLでgit clone・ブランチチェックアウト）
- MRに処理開始コメント投稿
- CLI実行・ProgressManager起動・アサイニー監視の並行実行
- botアサイン解除検知時の強制終了処理
- タイムアウト処理
- 正常完了・異常終了後の後処理（git push・コンテナ破棄・GitLabコメント・タスク状態更新）
- CLILogMaskerでPATマスク後にcli_logをDB保存
- **完了条件**: F-4フロー全体が動作する（CLIがコードを変更・プッシュする）
- **バリデーション**: テスト環境でE2E動作確認（T-07/T-08）

### T5-7: ConsumerWorker・TaskProcessorの実装
- `consumer/consumer.py`（RabbitMQからデキュー・TaskProcessorにディスパッチ）
- `consumer/task_processor.py`（task_typeでIssueToMRConverter/MRProcessorを選択）
- **完了条件**: RabbitMQからメッセージをデキューしてF-3/F-4処理が起動される
- **バリデーション**: Producer→Consumer の結合テスト実施

---

## フェーズ6: cli-execコンテナイメージ

### T6-1: Claude Code cli-execイメージ
- `cli-exec/claude/Dockerfile`（claude CLIのインストール）
- `docker-compose.yml` の `build-only` プロファイルに定義
- **完了条件**: `docker compose --profile build-only build` でイメージがビルドされる
- **バリデーション**: `docker run` でCLIが起動することを確認

### T6-2: opencode cli-execイメージ
- `cli-exec/opencode/Dockerfile`（opencode CLIのインストール）
- **完了条件**: `docker compose --profile build-only build` でイメージがビルドされる
- **バリデーション**: `docker run` でCLIが起動することを確認

---

## フェーズ7: テスト環境・セットアップスクリプト

### T7-1: docker-compose テスト環境設定
- `docker-compose.yml` の `test` プロファイルに GitLab CE コンテナ追加
- `docker-compose.yml` の `test` プロファイルに LiteLLM Proxy コンテナ追加
- `docker-compose.yml` に `test_playwright` サービス（`mcr.microsoft.com/playwright:v1.59.0`）を `test` プロファイルで追加
  - `e2e/` ディレクトリをマウント
- **完了条件**: `docker compose --profile test up` で全サービスが起動する
- **バリデーション**: `docker compose --profile test ps` で全サービスが running 状態であること

### T7-2: システムセットアップスクリプト
- `scripts/setup.sh`
- 初期管理者ユーザー作成
- F-3/F-4初期プロンプトテンプレートのDB投入
- 組み込みCLIアダプタ登録（claude・opencode）
- **完了条件**: `./scripts/setup.sh` 実行後にDBに初期データが投入される
- **バリデーション**: DBに管理者ユーザー・初期テンプレート・組み込みアダプタが存在すること

### T7-3: テスト用セットアップスクリプト
- `scripts/test_setup.sh`
- GitLab API経由でbotアカウント作成・PAT発行
- 対象プロジェクトへのWebhook設定登録
- テスト用プロジェクト作成・テストユーザーアカウント作成
- LiteLLM Proxy APIでテスト用Virtual Key発行・モデル転送設定登録
- **完了条件**: `./scripts/test_setup.sh` 実行後にテスト環境がT-01〜T-30実施可能な状態になる
- **バリデーション**: GitLab・LiteLLMに期待通りのリソースが作成されていること

---

## フェーズ8: E2Eテスト実装

### T8-1: E2Eテスト基盤（Playwright）
- `e2e/package.json`（playwright/test依存関係）
- `e2e/playwright.config.ts`（baseURL: `http://frontend:80`）
- **完了条件**: `docker compose run --rm test_playwright sh -c "npm install && npx playwright test"` が実行できる
- **バリデーション**: 空のテストスイートがエラーなく実行できること

### T8-2: 認証・認可 E2Eテスト（T-01, T-17〜T-22, T-27）
- ログイン成功・失敗（T-01ログイン部分）
- 一般ユーザーの自分の詳細閲覧（T-17）
- 一般ユーザーによる他ユーザー詳細・編集アクセス拒否（T-19, T-20）
- 一般ユーザーによるSC-02/SC-07アクセス拒否（T-21, T-27）
- メールアドレス重複登録エラー（T-22）
- **完了条件**: 全テストがパスする
- **バリデーション**: `npx playwright test` で全テストGREEN

### T8-3: ユーザー管理 E2Eテスト（T-01〜T-03, T-15, T-18）
- ユーザー作成（T-01）
- Virtual Key更新（T-02）
- デフォルトCLI・モデル変更（T-03）
- ユーザー削除（T-15）
- 一般ユーザーが自分の編集可能フィールドのみ変更できる（T-18）
- **完了条件**: 全テストがパスする

### T8-4: タスク実行 E2Eテスト（T-04〜T-16, T-24〜T-26, T-28〜T-30）
- Webhook検出によるMR変換（T-04）
- ポーリング検出によるMR変換（T-05）
- MRラベル・アサイン引き継ぎ（T-06）
- MR処理・CLI実行（T-07）
- CLI上書き指定（T-08）
- レビュアー未設定時のauthor Virtual Key使用（T-09）
- 未登録/無効ユーザー処理スキップ（T-10, T-13）
- botアサインのみ/ラベルのみでのスキップ（T-11, T-12）
- タスク履歴確認（T-14, T-23）
- docker-compose e2eテスト実行（T-16）
- 重複処理防止（T-24）
- プロンプトテンプレート変更（T-25）
- ユーザー個別テンプレートクリア（T-26）
- 進捗コメント更新（T-28, T-29）
- botアサイン解除による強制終了（T-30）
- **完了条件**: 全テストがパスする

---

## フェーズ9: ドキュメント整備

### T9-1: README.md作成
- システム概要
- 前提条件（Docker, docker-compose）
- 起動方法（本番・テスト環境）
- システムセットアップ手順
- 環境変数の説明
- E2Eテスト実行方法
- **完了条件**: README.mdが作成され、手順通りに操作できること

---

## フェーズ10: 最終確認

### T10-1: 全変更点の実装確認
- 詳細設計書 `docs/detail_design.md` の全設計項目が実装されているか確認
- 要件定義書 `docs/requirements.md` の全機能要件（F-1〜F-10）が実装されているか確認
- 全テストシナリオ（T-01〜T-30）のE2Eテストが実装・パスしているか確認
- **完了条件**: `docker compose --profile test up` → `./scripts/setup.sh` → `./scripts/test_setup.sh` → E2Eテスト実行でT-01〜T-30全てGREEN
- **バリデーション**: `npx playwright test` の出力が全テストPASS

### T10-2: セキュリティチェック
- Virtual Key暗号化・複合タイミングが設計通りか確認
- GitLab PATがDBに保存されていないか確認
- GitLab PATがcli-execコンテナの環境変数に渡されていないか確認
- CLIログのPATマスクが機能しているか確認
- JWT認証・ロールベースアクセス制御が全エンドポイントで機能しているか確認
- HMAC署名検証が機能しているか確認
- **完了条件**: 全セキュリティ要件が実装されていること
- **バリデーション**: セキュリティチェックリストの全項目確認
