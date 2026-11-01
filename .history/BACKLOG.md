# BACKLOG

## 作業中

- **Zscaler 環境対応**（ブランチ `feature/zscaler-support`）
  - 変更要件定義書・変更詳細設計書・tasks.md ができている（`.history/20261101-zscaler-support/`）。
  - 既存コードの isdd 化（正本 `docs/requirements.md`・`docs/detail_design.md` と対応表 `docs/trace_map.md`）と、Zscaler の変更の正本への反映は 2026-11-01 に済んだ。
  - tasks.md の実装は 2026-11-02 に済んだ。単体テスト 23 件、模擬プロキシでの通し確認、Zscaler 設定を無効にした通し確認が通った。
  - 実装は 2026-11-02 に `19522ca` でコミットした。
  - 実 LLM での確認（`./scripts/test_setup.sh --zscaler-mock --real --run-tests`）を 2026-11-02 に流した。Zscaler の E2E は 12 件通過。Playwright は Claude Code のシナリオが通り、opencode のシナリオ（T-31・T-32・T-34）は `.env` の `OPENAI_API_KEY` が空のため失敗した（opencode の既定のモデルが OpenAI の gpt-4o-mini）。2026-11-02 にユーザーの判断で、今回は流し直さないことにした。
  - 残り: 実装中に見つけた設計とのずれ（`docs/proposals.md` の 1〜3）を isdd-post-implementation-review で正本へ反映する。4（nginx の名前の引き直し）は正本へ反映済み。
- **opencode で Claude のモデルを使えるようにする**（新しい変更要求の候補。isdd-change-req から始める）
  - 今は opencode で Claude のモデルを選ぶと動かない。2026-11-02 に模擬の LiteLLM で確かめた。
  - 要るもの: consumer（`consumer/cli_adapter_resolver.py`）が Anthropic のモデルのときにキーを `ANTHROPIC_API_KEY` で渡すこと、宛先の末尾に `/v1` を付けること、LiteLLM の設定に opencode が呼ぶ小さいモデル `claude-haiku-5-5` を足す（または opencode の小さいモデルを指定する）こと。
  - できれば、本物の言語モデルでの opencode のシナリオ（T-31・T-32・T-34）を Claude のキーだけで流せる。

## テスト環境で気づいたこと

- Playwright の E2E の TS-A-6 が、1 回目に失敗し再試行で通ることがある（2026-11-01 の模擬プロキシでの通し確認）。2026-11-02 の無効での通し確認では 1 回目で通った。
- Playwright の E2E の users の T-01（管理者が新規ユーザーを登録できる）は、テスト用のユーザーが溜まると必ず失敗する（2026-11-02 に原因を特定）。管理画面のユーザー一覧の表は 1 画面 10 行で、並びはユーザー名の順。`gitlab_integration.spec.ts` が毎回作る `disabled-user-*` は消されずに残り、失敗した回の `e2e-test-user-*`・`e2e-dup-*` も残る。全体が 10 件を超えると、新しく作った `e2e-test-user-*` が 2 画面目に回って見えなくなる。T-22・T-15 は T-01 が作るユーザーを使うので、つられて失敗する（テスト用のユーザー名がファイルを読み込んだ時刻で決まり、再試行では別の名前になるため）。2026-11-02 はテスト用のユーザー 17 件を管理者の API で消して流し直した。直すなら、テストの後片付けか、T-01 での一覧の検索のどちらか。これとは別に、T-01 の 1 回目だけ、作成ボタンを押したあと 5 秒以内に一覧へ移らずに失敗することがある（テスト用のユーザーが溜まっていない回でも起きた。再試行で通る）。
- （直した）frontend の nginx は backend のアドレスを起動時に 1 回だけ引いていた（`frontend/nginx.conf` の `proxy_pass http://backend:8000`）。backend のコンテナだけが作り直されると、frontend が古いアドレスへつなぎ続けてログインが 502 になる。Zscaler の設定を変えてイメージを作り直したときに 2026-11-02 に起きた。同じ日に、nginx が要求のたびに名前を引き直すように直した（`docs/proposals.md` の 4）。
- OrbStack のマシンでは、コンテナで Playwright のブラウザを取得した直後の数十秒、外への最初の接続が詰まる（ERR_SOCKET_NOT_CONNECTED など）。公式の Playwright イメージでも同じ。Zscaler の E2E の標準のブラウザの確認は、開き直しを 3 回まで行うようにした。CLI のエージェントが対象リポジトリのテストで同じ目に遭うかもしれない。

## 不具合の可能性（逆引きで見つけた、既存の要件定義書とコードの食い違い）

2026-11-01 の逆引きで、正本にはコードの現状を書くと決めた。次の各項目を直すかどうかは、変更要求（isdd-change-req）として個別に決める。

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
| 12 | producer と consumer の `GITLAB_API_URL` が compose で `http://gitlab:8929` に固定され、本番の外部の GitLab を `.env` で指定しても効かない | `docker-compose.yml` |
| 13 | RabbitMQ への投入に失敗すると、tasks に pending の行が残り、その Issue／MR が二度と投入されない。壊れたメッセージは再配信され続ける | `producer/gitlab_event_handler.py`、`shared/messaging/rabbitmq_client.py` |
| 14 | 一部の E2E が名前どおりの内容を確かめていない（TTY 検知、Webhook の重複抑止など）。システムの F-4 テンプレートを上書きして後に残すテストがある | `e2e/tests/*.spec.ts` |
| 15 | 小さな不整合: F-3 のブランチの作成元が `main` 固定、F-3 の失敗でトリガーラベルが戻らない、F-3 は Task に CLI とモデルを記録しない、no-op 判定が英語の定型句 3 種に依存、F-4 のタイムアウトとアサイン解除でエラーコメントが 2 件出る、トークンの比較が定数時間の比較でない、一般ユーザーが CLI アダプタ一覧を取れない、管理者が他人や自分のパスワードを再設定できない、`/users/new` と同じ名前のユーザーの詳細画面に行けない、README と compose の記述のずれ | 各ファイル |
| 16 | 使われていない公開メソッド・スクリプトがある（CLIContainerManager の `start_container`・`write_file`・`configure_git`・`kill_process`・`get_container_pid`、ProgressManager の `start`、GitLabClient の `list_issues`・`list_merge_requests`・`branch_exists`、`scripts/gitlab_setup.py`、`shared/models/gitlab.py`、`get_project_ids`） | 各ファイル |
