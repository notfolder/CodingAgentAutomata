# opencode での Claude のモデルの利用 tasks

入力: `docs/requirements.md`・`docs/detail_design.md`（2026-11-02 に変更を反映済み）、`.history/20261102-opencode-claude-model/change_detail_design.md`。上から順に実行する。

---

## 0. isdd-setup 導入確認タスク

- 内容: `scripts/isdd/check.sh` があることを確かめる（導入済み。実行形態 container・認証あり・外部連携あり）。
- 完了条件: `bash scripts/isdd/check.sh` が実行でき、`scripts/isdd/completeness.json` の実行形態・認証・外部連携が詳細設計書（第 1 章、6-2、4-1-5）と一致している。
- 検証: `bash scripts/isdd/check.sh` と `cat scripts/isdd/completeness.json`。

## 0-2. 正本反映の確認タスク

- 内容: 変更要件の全 [追加] RQ-ID（`RQ-BK-OPENCODE-CLAUDE-MODEL`、`RQ-EF-SOFT-SAVING-OPENCODE-CLAUDE`、`RQ-FT-CALL-CLAUDE-VIA-OPENCODE`、`RQ-FT-DETERMINE-OPENCODE-PROVIDER`、`RQ-EX-USE-LOCAL-HTTP-MOCK`、`RQ-NF-OPENCODE-CLAUDE-NO-MIGRATION`、`RQ-TS-VERIFY-OPENCODE-CLAUDE-MODEL`）と、変更設計の全 [追加] DS-ID（11 章の 6 件）が正本にあることを確かめる。[削除] の ID は無い。
- 完了条件: `python3 ~/.claude/skills/isdd-traceable-coding/scripts/rq_ds_link_checker.py docs/requirements.md docs/detail_design.md`（スキルを置いた場所に読み替える）が合格する。未反映があれば実装を始めず isdd-change-design に戻る。
- 検証: 上のコマンドの出力。

---

## 1. opencode のプロバイダの判定と設定の組み立て

- 設計 ID: `DS-FN-DETERMINE-OPENCODE-PROVIDER-FT-DETERMINE-OPENCODE-PROVIDER`、`DS-FN-BUILD-OPENCODE-PROVIDER-CONFIG-FT-CALL-CLAUDE-VIA-OPENCODE`（置き場所は `DS-MD-CONSUMER-CLI-ADAPTER-RESOLVER-FT-RESOLVE-CLI-ADAPTER`）
- 内容: `consumer/cli_adapter_resolver.py` の CLIAdapterResolver に、静的メソッド `split_opencode_model` と `build_opencode_provider_config` を足す（詳細設計書 5-2）。`build_env_vars` の中の既存のプロバイダの組み立てを、この 2 つの呼び出しに置き換える。`build_env_vars` の引数の `info` の Virtual Key（`llm_api_key`）を `build_opencode_provider_config` に渡す。CLI アダプタ設定（`scripts/setup.py` の組み込みの定義）は変えない。
- 完了条件: プロバイダが `anthropic` のとき、`OPENCODE_CONFIG_CONTENT` の JSON に `/v1` 付きの `baseURL`・`apiKey`・`small_model` が入る。`openai` と `/` の無い名前では、JSON が変更前と同じになる。Claude Code のアダプタの出力は変わらない。
- 検証: 2 の単体テスト。

## 2. 単体テスト

- 設計 ID: `DS-TS-OPENCODE-PROVIDER-CONFIG-UNIT-FT-CALL-CLAUDE-VIA-OPENCODE`
- 内容: `tests/consumer/test_cli_adapter_resolver_opencode.py` を作り、詳細設計書 8-2 の単体テストの行の 6 項目を確かめる。DB は使わず、CLI アダプタ設定はテストの中でオブジェクトを作って渡す。
- 完了条件: 6 項目のテストがすべて通る。
- 検証: `docker compose --profile test run --rm unit_test` を `./scripts/compose.sh --profile test run --rm unit_test` の形で実行する（`docker compose` を直接使わない決まりのため）。

## 3. モック LLM モードの LiteLLM Proxy の設定

- 設計 ID: `DS-OP-MOCK-LITELLM-DROP-PARAMS-EX-USE-LOCAL-HTTP-MOCK`
- 内容: `litellm/config.yml` に `litellm_settings` を足し、`drop_params: true` を置く。`litellm/config-real.yml` は変えない。
- 完了条件: モック LLM モードで、opencode から `anthropic/claude-opus-5-5` と `anthropic/claude-haiku-4-5-20251001` を呼んだとき、LiteLLM Proxy の `/v1/messages` が 200 を返す。
- 検証: 4 の E2E（モック LLM モード）。

## 4. E2E シナリオ（T-35）

- 設計 ID: `DS-TS-OPENCODE-CLAUDE-MODEL-E2E-TS-VERIFY-OPENCODE-CLAUDE-MODEL`
- 内容: `e2e/tests/gitlab_integration.spec.ts` に T-35 を足す（詳細設計書 8-2 の行のとおり）。ブランチと Draft MR を GitLab API で直接作り、説明文に `agent: cli=opencode model=anthropic/<DEFAULT_CLAUDE_MODEL>` の行を入れる。完了コメントと、backend のタスクの一覧の CLI・モデル・状態を確かめる。ファイル先頭のテストの一覧のコメントにも T-35 を足す。
- 完了条件: モック LLM モードで T-35 が通る。
- 検証: `./scripts/test_setup.sh --run-tests`。

## 5. 移行の確認

- 設計 ID: `DS-OP-OPENCODE-CLAUDE-NO-MIGRATION-NF-OPENCODE-CLAUDE-NO-MIGRATION`
- 内容: 既存の DB（組み込みの opencode のアダプタの `env_mappings` が `OPENAI_API_KEY` のまま）で、consumer のイメージを作り直して起動し直すだけで T-35 が通ることを確かめる。初期セットアップは再実行しない。
- 完了条件: DB の CLI アダプタ設定を書き換えずに、T-35 が通る。
- 検証: 4 の E2E を流したテスト環境で、CLI アダプタ設定の `env_mappings` が変わっていないことを backend の CLI アダプタ API で確かめる。

---

## 6. 対応表（docs/trace_map.md）更新タスク

- 内容: `split_opencode_model` と `build_opencode_provider_config` の行を `docs/trace_map.md` に足す（書式は trace-map-rules.md。関数の行）。
- 完了条件: `bash scripts/isdd/check.sh --strict` がエラー 0 件・警告 0 件で通る。
- 検証: 上のコマンドの出力。

## 7. 起動確認タスク

- 内容: 実行形態はコンテナ。`./scripts/compose.sh up -d --build` で全サービスが起動することを確かめる（`docker compose` を直接使わない決まりのため）。
- 完了条件: 全サービスがエラーなく起動する。
- 検証: `./scripts/compose.sh ps` で全サービスが動いている。

## 8. 単体テスト・結合テスト全件通過タスク

- 内容: 詳細設計書 8-5 の実行コマンドで、単体テストと結合テストを全件実行する。
- 完了条件: FAIL が 0 件。失敗したら修正と再実行を繰り返す。
- 検証: `./scripts/compose.sh --profile test run --rm unit_test` の出力。

## 9. E2E テスト全件通過タスク

- 内容: `e2e/` 配下のテストを、モック LLM モードで全件実行する。Zscaler まわりは変えないので、模擬プロキシありと `ZSCALER_ENABLED=false` の両方の通し確認は必須にしない（`.env` の設定のまま 1 回流す）。
- 完了条件: FAIL が 0 件。失敗したら修正と再実行を全件成功まで続ける。実 LLM モード（`./scripts/test_setup.sh --real --run-tests`）は手動実行で、T-35 と、デフォルトモデルを Claude にした opencode の既存のシナリオ（T-31・T-32・T-34。`.env` の `DEFAULT_OPENAI_MODEL_LITELLM` を `anthropic/claude-haiku-4-5-20251001` にする）を流す。
- 検証: `./scripts/test_setup.sh --run-tests` の出力。

## 10. README.md 記載タスク

- 内容: 対象外（起動方法と初期ユーザーは変わらず、運用要件にも README の変更が無いため）。
- 完了条件: README の起動方法と初期ユーザーの記載が、変更後もそのまま正しい。
- 検証: README の「起動方法」を読み、変更で手順が変わっていないことを確かめる。

## 11. 実装完了チェックタスク

- 内容: `python3 scripts/isdd/implementation_completeness_checker.py .` を実行する。
- 完了条件: 全項目が OK。外部連携の連携ライブラリ（`external/litellm/src/`）が無いことで NG になる場合は、詳細設計書 4-1-5 の「連携ライブラリを置かない」決定（2026-11-02）を根拠に、チェッカーの扱いを報告して判断を仰ぐ。
- 検証: 上のコマンドの出力。

## 12. すべての変更点の実装確認タスク

- 内容: 変更設計書 11 章の 6 件の設計 ID がすべて実装され、対応表にあることを確かめる。
- 完了条件: 6 件すべてについて、コード（またはテスト・設定）と対応表の行がある。
- 検証: `bash scripts/isdd/check.sh --strict` と、変更設計書 11 章との突き合わせ。

---

設計中に変更要件定義書を直したことは無い（外部調査の段階で 3-3 にモックの方式の行を足したのは、設計の前の isdd-external-research で行った）。
