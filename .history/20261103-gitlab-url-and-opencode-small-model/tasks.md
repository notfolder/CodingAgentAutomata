# 本番の GitLab の URL と opencode のタイトル用のモデル tasks

入力: `.history/20261103-gitlab-url-and-opencode-small-model/change_requirements.md`、`change_detail_design.md`、正本 `docs/requirements.md`・`docs/detail_design.md`。上から順に実行する。

---

## 0. isdd-setup 導入確認タスク

- 内容: `scripts/isdd/check.sh` があり、`scripts/isdd/VERSION` がスキルの版（v2.1.0）と同じことを確かめる。2026-11-03 の時点では `scripts/isdd/VERSION` が v2.0.0 で、進行中の変更（`docs/active_change`）を読まないので、`isdd-setup` を実行し直して v2.1.0 にする（実行形態 container・認証あり・外部連携ありを渡す）。
- 完了条件: `bash scripts/isdd/check.sh` が実行でき、`scripts/isdd/completeness.json` が実行形態 container・認証あり・外部連携ありで、詳細設計書と一致する。
- 検証: `bash scripts/isdd/check.sh` と `cat scripts/isdd/completeness.json`。

## 0-2. 進行中の変更の登録確認タスク

- 内容: `docs/active_change` の 1 行目が `.history/20261103-gitlab-url-and-opencode-small-model/` を指していることを確かめる。正本には変更を反映しない。
- 完了条件: `bash scripts/isdd/check.sh` の出力に「進行中の変更」の行があり、`rq_ds_link_checker.py .history/20261103-gitlab-url-and-opencode-small-model/change_requirements.md .history/20261103-gitlab-url-and-opencode-small-model/change_detail_design.md --base docs/requirements.md` が合格する。
- 検証: 上の 2 つのコマンドの出力。

---

## 1. 変更前の再現の確認

- 設計 ID: `DS-TS-OPENCODE-NO-UNKNOWN-MODEL-CALL-E2E`（確かめる対象）
- 内容: コードを変える前に、今のテスト環境（モック LLM モード）で T-31（opencode の OpenAI の経路の Issue→MR 変換）だけを流し、LiteLLM Proxy のログにタイトル用のモデルの `Invalid model name passed in model=` が出ることを確かめる。流す前の時刻（UTC）を控え、`docker compose logs --since <時刻> litellm` で見る。
- 完了条件: 該当する行が 1 件以上あり、モデル名（`gpt-5.4-nano-flex` など）を記録した。出なければ、実装に進まずに報告し、確かめ方を見直す（このシナリオでは直ったことを確かめられないため）。
- 検証: `./scripts/compose.sh --profile test run --rm test_playwright sh -c "npm install --silent && npx playwright test -g 'T-31'"` と上のログの確認。

## 2. compose の GitLab の URL の置き換えをやめる

- 設計 ID: `DS-OP-COMPOSE-GITLAB-URL`
- 内容: `docker-compose.yml` の producer・consumer・test_playwright・test_playwright_real の `environment` から、`GITLAB_API_URL` の行と、その上の「localhost の URL を内部名で上書き」のコメントを取り除く。
- 完了条件: `docker-compose.yml` に `GITLAB_API_URL:` の行が無い。
- 検証: `grep -n "GITLAB_API_URL" docker-compose.yml` が 0 件。7 のホストの E2E。

## 3. テスト環境の構築の GitLab の URL の扱い

- 設計 ID: `DS-OP-TEST-ENVIRONMENT`
- 内容: 変更設計 9-1 の ①〜⑤ を実装する。
  - `scripts/test_setup.sh`: ホストから見た URL を `http://localhost:8929` に決めて `test_setup.py` に渡す。`.env.test` を読み込んだ直後に、ホストで使う `GITLAB_API_URL` をその値に戻す。構築の最初に `.env` のハッシュを取る。ステップ 7 の直前の時刻（UTC）と LiteLLM Proxy のサービス名を控える。この 3 つを環境変数でステップ 8 に渡す。ステップ 8 の表示を「ホストから確かめる E2E」に改める。
  - `scripts/test_setup.py`: `.env.test` の `GITLAB_API_URL` に、`GITLAB_CONTAINER_URL`（既定 `http://gitlab:8929`）を書く。
- 完了条件: 構築の後、`.env.test` の `GITLAB_API_URL` が `http://gitlab:8929` で、`.env` が書き換わっていない。後片付けの GitLab の呼び出しが、ホストから見た URL で成功する。
- 検証: 11 の E2E。

## 4. opencode の設定の組み立て

- 設計 ID: `DS-FN-BUILD-OPENCODE-CONFIG`
- 内容: `consumer/cli_adapter_resolver.py` の `build_opencode_provider_config` で、`small_model` を入れる処理をプロバイダの分岐の外に出し、どのプロバイダでも `qualify_opencode_model` の結果を入れる。docstring も直す。
- 完了条件: `gpt-5.5` で `small_model` が `openai/gpt-5.5` になり、`anthropic` の JSON は既存と同じ。
- 検証: 5 の単体テスト。

## 5. 単体テスト

- 設計 ID: `DS-TS-OPENCODE-RESOLVER-UNIT`
- 内容: `tests/consumer/test_cli_adapter_resolver_opencode.py` を、変更設計 8-1 の ①〜⑤ に直す。`openai` の名前で `small_model` を入れない前提のテストは、`small_model` が入ることを確かめるテストに改める。
- 完了条件: すべて通る。
- 検証: `ZSCALER_ENABLED=false ./scripts/compose.sh --profile test run --rm --build unit_test`。

## 6. ホストの E2E

- 設計 ID: `DS-TS-GITLAB-URL-FROM-ENV-E2E`、`DS-TS-TEST-SETUP-REPEATABLE-E2E`、`DS-TS-OPENCODE-NO-UNKNOWN-MODEL-CALL-E2E`
- 内容: `e2e/zscaler/test_runtime_settings_e2e.py` を作り、変更設計 8-2 の 3 つのシナリオを書く。`conftest.py` の `run`・`REPO` を使う。test_setup.sh から渡る環境変数（開始時刻、LiteLLM Proxy のサービス名、`.env` のハッシュ）が無いときは、それを使うテストを飛ばす。
- 完了条件: 単独で実行すると、GitLab の URL のテストが通り、ほかの 2 つは飛ばされる。
- 検証: `.venv-test-setup/bin/python3 -m pytest e2e/zscaler/test_runtime_settings_e2e.py -q -p no:cacheprovider`。

## 6-2. opencode の Claude の経路の Issue→MR 変換の E2E（T-36）

- 設計 ID: `DS-TS-OPENCODE-CLAUDE-ISSUE-TO-MR-E2E`
- 内容: `e2e/tests/gitlab_integration.spec.ts` に T-36 を足す（変更設計 8-2 の ①〜⑤）。デフォルトモデルを戻す処理は、失敗しても必ず通る位置に置く。ファイル先頭のテストの一覧のコメントにも足す。
- 完了条件: モック LLM モードで T-36 が通り、テストの後に opencode のテストユーザーのデフォルトモデルが元に戻っている。
- 検証: 11 の E2E。

## 7. README

- 設計 ID: `DS-OP-GITLAB-URL-README`
- 内容: 変更設計 9-1 のとおり、環境変数の表の `GITLAB_API_URL` の説明と、更新の注意（本番の手直しを戻す、手元は構築を実行し直す）を書く。
- 完了条件: README に compose の手直しを前提にした記述が無く、更新の注意がある。
- 検証: `grep -n "GITLAB_API_URL" README.md` で説明を読む。

---

## 8. 対応表（docs/trace_map.md）更新タスク

- 内容: `DS-FN-BUILD-OPENCODE-PROVIDER-SETTINGS-FT-CALL-CLAUDE-VIA-OPENCODE` の行を `DS-FN-BUILD-OPENCODE-CONFIG` に差し替える。ほかに足すソースファイル・クラス・公開関数は無い。
- 完了条件: `bash scripts/isdd/check.sh --strict` がエラー 0 件・警告 0 件。
- 検証: 上のコマンドの出力。

## 9. 起動確認タスク

- 内容: 11 の E2E の中で、テスト環境の全サービスが起動することを確かめる。
- 完了条件: 起動がエラーなく終わる。
- 検証: 11 のコマンドの出力のステップ 1・6。

## 10. 単体テスト・結合テスト全件通過タスク

- 内容: 単体テストを全件流す。
- 完了条件: FAIL が 0 件。
- 検証: `ZSCALER_ENABLED=false ./scripts/compose.sh --profile test run --rm --build unit_test`。

## 11. E2E テスト全件通過タスク

- 内容: テスト環境の構築とテスト用の設定ファイルの扱いを変えるので、Zscaler 設定を無効にした実行と、模擬プロキシありの実行の両方で全件を流す。2 回続けて流すことで、2 回目が「構築を続けて実行しても同じ状態になる」の確認を兼ねる。
- 完了条件: どちらも FAIL が 0 件。2 回目で、ホストの E2E の 3 つのシナリオがすべて通る（飛ばされない）。
- 検証: `ZSCALER_ENABLED=false ./scripts/test_setup.sh --run-tests` に続けて `./scripts/test_setup.sh --zscaler-mock --run-tests`。

## 12. README.md 記載タスク

- 内容: 起動方法と初期ユーザーは変わらない。更新の注意は 7 で書いた。
- 完了条件: README の「起動方法」の記載が、変更後も正しい。
- 検証: README の「起動方法」を読む。

## 13. 実装完了チェックタスク

- 内容: `python3 scripts/isdd/implementation_completeness_checker.py .` を実行する。
- 完了条件: 全項目が OK。
- 検証: 上のコマンドの出力。

## 14. すべての変更点の実装確認タスク

- 内容: 変更設計 11 章の [追加] の DS-ID が実装と対応表にあり、[削除] の DS-ID（`DS-FN-BUILD-OPENCODE-PROVIDER-SETTINGS-FT-CALL-CLAUDE-VIA-OPENCODE`、`DS-TS-OPENCODE-MODEL-NAME-UNIT-FT-DETERMINE-OPENCODE-PROVIDER-BY-NAME`、`DS-OP-TEST-ENVIRONMENT-FT-SETUP-TEST-ENVIRONMENT`）が対応表に残っていないことを確かめる。
- 完了条件: 上のとおり。
- 検証: `bash scripts/isdd/check.sh --strict` と、[削除] の ID の `docs/trace_map.md` の検索が 0 件。
