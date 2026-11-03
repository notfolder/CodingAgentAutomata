# opencode のモデル名の判定を本番の名前に合わせる tasks

入力: `docs/requirements.md`・`docs/detail_design.md`（2026-11-03 に変更を反映済み）、`.history/20261103-opencode-model-name-rule/change_detail_design.md`。上から順に実行する。

---

## 0. isdd-setup 導入確認タスク

- 内容: `scripts/isdd/check.sh` があり、`scripts/isdd/VERSION` がスキルの版（v2.0.0）と同じことを確かめる。
- 完了条件: `bash scripts/isdd/check.sh` が実行でき、`scripts/isdd/completeness.json` が実行形態 container・認証あり・外部連携ありで、詳細設計書と一致する。
- 検証: `bash scripts/isdd/check.sh` と `cat scripts/isdd/completeness.json`。

## 0-2. 正本反映の確認タスク

- 内容: [追加] の `RQ-BK-OPENCODE-UNPREFIXED-MODEL-NAMES`・`RQ-FT-DETERMINE-OPENCODE-PROVIDER-BY-NAME`・`RQ-TS-VERIFY-OPENCODE-UNPREFIXED-CLAUDE-MODEL` と、変更設計 11 章の [追加] の DS-ID 4 件が正本にあり、[削除] の RQ-ID 2 件・DS-ID 4 件が正本に無いことを確かめる。
- 完了条件: `rq_ds_link_checker.py docs/requirements.md docs/detail_design.md` が合格する。
- 検証: 上のコマンドの出力と、[削除] の ID の検索が 0 件であること。

---

## 1. モデル名の判定とつなぎ

- 設計 ID: `DS-FN-DETERMINE-OPENCODE-PROVIDER-BY-NAME-FT-DETERMINE-OPENCODE-PROVIDER-BY-NAME`
- 内容: `consumer/cli_adapter_resolver.py` の `split_opencode_model` を新しい判定（`/` が無ければ `claude-` で始まるかで決める）にし、`qualify_opencode_model` を足す。`build_start_command` は、アダプタに設定の JSON を渡す環境変数があるときだけ、`{model}` に `qualify_opencode_model` の結果を入れる。
- 完了条件: 詳細設計書 4-1-5 の表のとおりに判定とつなぎができ、Claude Code の起動コマンドは変わらない。
- 検証: 3 の単体テスト。

## 2. 設定の組み立て

- 設計 ID: `DS-FN-BUILD-OPENCODE-PROVIDER-SETTINGS-FT-CALL-CLAUDE-VIA-OPENCODE`
- 内容: `build_opencode_provider_config` の `small_model` を、`qualify_opencode_model` の結果にする。判定は 1 の `split_opencode_model` を使う。
- 完了条件: `claude-opus-5-5` でも `anthropic/claude-opus-5-5` でも、`small_model` が `anthropic/claude-opus-5-5` になる。
- 検証: 3 の単体テスト。

## 3. 単体テスト

- 設計 ID: `DS-TS-OPENCODE-MODEL-NAME-UNIT-FT-DETERMINE-OPENCODE-PROVIDER-BY-NAME`
- 内容: `tests/consumer/test_cli_adapter_resolver_opencode.py` を、詳細設計書 8-2 の単体テストの行の内容に直す（判定、つなぎ、起動コマンド、設定の JSON、`build_env_vars`）。
- 完了条件: すべて通る。
- 検証: `ZSCALER_ENABLED=false ./scripts/compose.sh --profile test run --rm --build unit_test`（単体テストのコンテナはネットワークを使わないため）。

## 4. E2E（T-35）

- 設計 ID: `DS-TS-OPENCODE-UNPREFIXED-CLAUDE-E2E-TS-VERIFY-OPENCODE-UNPREFIXED-CLAUDE-MODEL`
- 内容: `e2e/tests/gitlab_integration.spec.ts` の T-35 のエージェント指定を、プロバイダ名を付けない `DEFAULT_CLAUDE_MODEL`（既定 `claude-haiku-4-5-20251001`）にし、タスクの記録もその名前で確かめる。テスト名とファイル先頭の一覧のコメントも直す。
- 完了条件: モック LLM モードで T-35 が通る。
- 検証: 7 の E2E。

---

## 5. 対応表（docs/trace_map.md）更新タスク

- 内容: [削除] の DS-ID 2 件（関数）の行を、[追加] の DS-ID に差し替え、`qualify_opencode_model` の行を足す。
- 完了条件: `bash scripts/isdd/check.sh --strict` がエラー 0 件・警告 0 件。
- 検証: 上のコマンドの出力。

## 6. 起動確認と単体テスト全件通過タスク

- 内容: 7 の E2E の中で全サービスが起動することを確かめる。単体テストは 3 のコマンドで全件流す。
- 完了条件: 起動がエラーなく終わり、単体テストの FAIL が 0 件。
- 検証: 上のとおり。

## 7. E2E テスト全件通過タスク

- 内容: モック LLM モードで全件を流す。Zscaler まわりは変えないので、模擬プロキシありの 1 回だけ流す。
- 完了条件: FAIL が 0 件。
- 検証: `./scripts/test_setup.sh --zscaler-mock --run-tests`。

## 8. README.md 記載タスク

- 内容: 対象外（起動方法と初期ユーザーは変わらない）。
- 完了条件: README の起動方法の記載が、変更後も正しい。
- 検証: README の「起動方法」を読む。

## 9. 実装完了チェックタスク

- 内容: `python3 scripts/isdd/implementation_completeness_checker.py .` を実行する。
- 完了条件: 全項目が OK。
- 検証: 上のコマンドの出力。

## 10. すべての変更点の実装確認タスク

- 内容: 変更設計 11 章の [追加] 4 件が実装と対応表にあり、[削除] 4 件がコードと対応表に残っていないことを確かめる。
- 完了条件: 上のとおり。
- 検証: `bash scripts/isdd/check.sh --strict` と、[削除] の ID の検索。
