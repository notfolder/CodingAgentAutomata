# IDEAS

## 逆引きで見つけた不具合の候補

2026-11-01 の逆引きで、正本にはコードの現状を書くと決めた。次の各項目を直すかどうかは、変更要求（isdd-change-req）として個別に決める（追加 2026-11-01）。

| # | 内容 | 根拠（ファイル） |
|---|---|---|
| 1 | TTY 入力待機検知が動いていない。検知の部品（TTYWaitDetector、EBPFEnvironmentChecker、MRProcessor の TTY 失敗報告）が本番の処理から呼ばれていない | `consumer/tty_wait_detector.py`、`consumer/ebpf_environment_checker.py`、`consumer/mr_processor.py` |
| 2 | System Hook への切り替え（`.history/20260504-switch-to-system-hook`）は設計だけで、コードは Group Webhook のまま | `scripts/test_setup.py` |
| 3 | Webhook の重複受信の抑止が効かない。コードは `X-Idempotency-Key` を読むが、GitLab が送るのは `Idempotency-Key` | `producer/webhook_server.py` |
| 4 | MR の Webhook で、bot のアサインを単数形の `assignee` だけで判定している。GitLab の MR の Webhook には `assignees` しか無いため、MR は Webhook では拾われず、ポーリングだけで拾われると推測 | `producer/gitlab_event_handler.py` |
| 5 | GitLab クライアントの例外の分岐（404 を None、401/403 を即時の例外）が、python-gitlab 8.6 の例外の種類と合わずに効いていない。429 の再試行の数え方もコメントと違う | `shared/gitlab_client/gitlab_client.py` |
| 6 | F-4 のアサイン監視が、GitLab の一時的な失敗で止まっただけでも「bot が外された」として CLI を強制終了する | `consumer/mr_processor.py` |
| 7 | 画面で値をクリアしても保存されない（画面は null を送り、API は null を「変更しない」と扱う）。F-4 テンプレート、個別 MCP 設定、システム設定、CLI アダプタの設定内容の環境変数名が対象 | `backend/services/*`、`frontend/src/views/*` |
| 8 | Virtual Key が二重にマスクされて表示される（`********abcd`） | `frontend/src/views/UserDetailView.vue` |
| 9 | F-3 と F-4 で MCP 設定の形が違う（F-4 は `mcpServers` で包まないため、opencode に MCP 設定が渡らない） | `consumer/issue_to_mr_converter.py`、`consumer/mr_processor.py` |
| 10 | Virtual Key の検証を、ユーザーの作成時には行わない（更新時だけ行う）。LiteLLM に接続できないときは有効とみなして保存する | `backend/services/user_service.py`、`backend/services/model_candidate_service.py` |
| 11 | タスクを持つユーザーの削除と、タスクから参照されている CLI アダプタの削除で、DB の参照の扱いが決まっていない（500 になるか、履歴の CLI 情報が消えると推測） | `shared/models/db.py`、`backend/services/*` |
| 12 | （2026-11-03 に解消。`.history/20261103-gitlab-url-and-opencode-small-model/`）producer と consumer の `GITLAB_API_URL` が compose で `http://gitlab:8929` に固定され、本番の外部の GitLab を `.env` で指定しても効かない | `docker-compose.yml` |
| 13 | RabbitMQ への投入に失敗すると、tasks に pending の行が残り、その Issue／MR が二度と投入されない。壊れたメッセージは再配信され続ける | `producer/gitlab_event_handler.py`、`shared/messaging/rabbitmq_client.py` |
| 14 | 一部の E2E が名前どおりの内容を確かめていない（TTY 検知、Webhook の重複抑止など）。システムの F-4 テンプレートを上書きして後に残すテストがある | `e2e/tests/*.spec.ts` |
| 15 | 小さな不整合: F-3 のブランチの作成元が `main` 固定、F-3 の失敗でトリガーラベルが戻らない、F-3 は Task に CLI とモデルを記録しない、no-op 判定が英語の定型句 3 種に依存、F-4 のタイムアウトとアサイン解除でエラーコメントが 2 件出る、トークンの比較が定数時間の比較でない、一般ユーザーが CLI アダプタ一覧を取れない、管理者が他人や自分のパスワードを再設定できない、`/users/new` と同じ名前のユーザーの詳細画面に行けない、README と compose の記述のずれ | 各ファイル |
| 16 | 使われていない公開メソッド・スクリプトがある（CLIContainerManager の `start_container`・`write_file`・`configure_git`・`kill_process`・`get_container_pid`、ProgressManager の `start`、GitLabClient の `list_issues`・`list_merge_requests`・`branch_exists`、`scripts/gitlab_setup.py`、`shared/models/gitlab.py`、`get_project_ids`） | 各ファイル |

## テスト環境の記録

- OrbStack のマシンでは、コンテナで Playwright のブラウザを取得した直後の数十秒、外への最初の接続が詰まる（ERR_SOCKET_NOT_CONNECTED など）。公式の Playwright イメージでも同じ。CLI のエージェントが対象リポジトリのテストで同じ目に遭うかもしれない（追加 2026-11-02）
- 管理画面のユーザー作成は bcrypt（コスト 12）でパスワードをハッシュにするため、CLI コンテナなどが CPU を使っていると数秒かかる（追加 2026-11-02）
- テスト環境の構築（`test_setup.py`）は、すでにいるテストユーザーのデフォルトモデルを `.env` の値に書き換えない（登録が 409 になると飛ばす）。`.env` のモデルを変えても、T-13・T-33・T-34 がユーザーを書き換えるまでは古いモデルで流れる（追加 2026-11-03）
