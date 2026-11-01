# Zscaler 環境対応 tasks

入力: `docs/requirements.md`・`docs/detail_design.md`（2026-11-01 に変更を反映済み）、`.history/20261101-zscaler-support/change_detail_design.md`。上から順に実行する。

---

## 0. isdd-setup 導入確認タスク

- 内容: `scripts/isdd/check.sh` があることを確かめる（2026-11-01 に導入済み。実行形態 container・認証あり・外部連携あり）。
- 完了条件: `bash scripts/isdd/check.sh` が実行でき、`scripts/isdd/completeness.json` の実行形態・認証・外部連携が詳細設計書（第 1 章、6-2、4-1-5）と一致している。
- 検証: `bash scripts/isdd/check.sh` と `cat scripts/isdd/completeness.json`。

## 0-2. 正本反映の確認タスク

- 内容: 変更要件の全 [追加] RQ-ID と変更設計の全 [追加] DS-ID が正本にあり、[削除] の ID（`DS-OP-CLI-EXEC-IMAGES-FT-BUILD-CLI-IMAGES`）が正本に無いことを確かめる。
- 完了条件: `python3 .claude/skills/isdd-traceable-coding/scripts/rq_ds_link_checker.py docs/requirements.md docs/detail_design.md`（スキルを置いた場所に読み替える）が合格する。未反映があれば実装を始めず isdd-change-design に戻る。
- 検証: 上のコマンドの出力。

---

## 1. `.env` の読み込みの共通化

- 設計 ID: `DS-MD-ENV-LOADER-UI-ZSCALER-ENV-SETTINGS`、`DS-MD-SCRIPTS-TEST-SETUP-SH-FT-SETUP-TEST-ENVIRONMENT`
- 内容: `scripts/test_setup.sh` の `.env` の読み込みを `scripts/lib/env.sh` に移し、`test_setup.sh` から読み込んで使う。動作は変えない。
- 完了条件: `./scripts/test_setup.sh` が今と同じ値で `.env` を読む。
- 検証: 8 の単体テストで、`.env` の読み込みの結果（コメント・空行・引用符の扱い）を確かめる。

## 2. Zscaler 設定の準備処理

- 設計 ID: `DS-MD-ZSCALER-LIB-FT-RESOLVE-CERT-BUNDLE`、`DS-MD-ZSCALER-PREPARE-CMD-FT-REQUIRE-ZSCALER-SETTINGS`、`DS-FN-RESOLVE-CERT-BUNDLE-FT-RESOLVE-CERT-BUNDLE`、`DS-FN-BUILD-NO-PROXY-LIST-FT-BUILD-NO-PROXY-LIST`、`DS-FN-REQUIRE-ZSCALER-SETTINGS-FT-REQUIRE-ZSCALER-SETTINGS`、`DS-FN-VERIFY-TRUST-BEFORE-USE-FT-VERIFY-ZSCALER-TRUST-BEFORE-USE`、`DS-FN-PREPARE-ZSCALER-FT-APPLY-ZSCALER-SETTINGS-RUNTIME`、`DS-IF-ZSCALER-PREPARE-CMD-FT-REQUIRE-ZSCALER-SETTINGS`、`DS-IF-ZSCALER-ENV-SETTINGS-UI-ZSCALER-ENV-SETTINGS`、`DS-SC-ZSCALER-SETTINGS-ENV-DT-ZSCALER-SETTINGS-ENV`、`DS-SC-ZSCALER-CERT-FILE-DT-ZSCALER-CERT-FILE`、`DS-SC-ZSCALER-GENERATED-DIR-FT-RESOLVE-CERT-BUNDLE`
- 内容: 詳細設計書 4-1-6・4-2-5 のとおり、`scripts/lib/zscaler.sh` と `scripts/zscaler_prepare.sh` を作る（`--mock`、`--project-dir`、`--host-bundle`）。生成物 `.zscaler/` を一時ディレクトリに作ってから置き換える。
- 完了条件: 4-1-6 のエラー①〜④がそれぞれの表示と終了コード 1 で止まり、成功時に生成物の 6 つのファイルができる。
- 検証: 8 の単体・結合テスト。

## 3. compose の入口スクリプト

- 設計 ID: `DS-MD-COMPOSE-WRAPPER-FT-REQUIRE-ZSCALER-SETTINGS`、`DS-IF-COMPOSE-WRAPPER-FT-REQUIRE-ZSCALER-SETTINGS`
- 内容: `scripts/compose.sh` を作る（準備処理 → `build.env` を環境に入れる → `docker compose "$@"`）。
- 完了条件: 準備処理が失敗したら docker compose を実行せずに同じ終了コードで終わる。
- 検証: 9 の E2E（設定の不足で止まるシナリオ）。

## 4. イメージ内の証明書の導入処理

- 設計 ID: `DS-MD-INSTALL-CA-FT-APPLY-ZSCALER-SETTINGS-BUILD`、`DS-FN-INSTALL-CA-SYSTEM-FT-APPLY-ZSCALER-SETTINGS-BUILD`、`DS-FN-INSTALL-CA-NSS-FT-APPLY-ZSCALER-SETTINGS-CLI-BROWSER`
- 内容: 詳細設計書 4-2-6 のとおり `scripts/zscaler/install-ca.sh`（POSIX sh）を作る。準備処理が `.zscaler/` へ写す。
- 完了条件: 状態が disabled なら何もしない。enabled でプロキシの宛先が無ければ失敗する。Debian・Ubuntu・Alpine の各土台で OS の束に証明書が入る。`nss` 指定で利用者の証明書データベースに入る。
- 検証: 5・6 のビルドと、9 の E2E。

## 5. 部品の Dockerfile

- 設計 ID: `DS-OP-DOCKERFILE-ZSCALER-BUILD-FT-APPLY-ZSCALER-SETTINGS-BUILD`
- 内容: backend・producer・consumer・frontend（ビルド段）の Dockerfile に、追加のビルドコンテキスト `zscaler` をマウントした導入処理と、4-2-6 の環境変数を足す。consumer に pytest 9.2.0 のテスト段を足す。
- 完了条件: Zscaler 設定を無効にした状態で今と同じようにビルドでき、有効な状態で模擬プロキシ経由でビルドできる。
- 検証: `./scripts/compose.sh build`（無効）と、9 の E2E（模擬経由のビルド）。

## 6. CLI コンテナの Ubuntu の共通の土台

- 設計 ID: `DS-OP-CLI-EXEC-UBUNTU-BASE-FT-RUN-STANDARD-BROWSERS-CLI-CONTAINER`、`DS-MD-DIND-START-FT-RUN-STANDARD-BROWSERS-CLI-CONTAINER`、`DS-FN-START-DIND-AND-RUN-CLI-FT-RUN-STANDARD-BROWSERS-CLI-CONTAINER`、`DS-FN-CONFIGURE-INNER-DOCKER-PROXY-FT-PASS-ZSCALER-SETTINGS-CLI-CONTAINER`
- 内容: 詳細設計書 9-1 のとおり `cli-exec/base/Dockerfile` と `cli-exec/base/dind-start.sh` を作り、`cli-exec/claude/Dockerfile` と `cli-exec/opencode/Dockerfile` を土台の上の作りに書き換える（旧 `docker:26-dind` の作りを消す）。イメージ名は変えない。
- 完了条件: 両方のイメージで、中の Docker デーモン・Node.js 24・Python・uv・Claude Code／opencode が動き、Claude Code は利用者 claude で動く。Playwright の Chromium と WebKit を取得して起動できる。
- 検証: 9 の E2E（標準のブラウザ、既存の E2E の全件）。

## 7. compose の変更

- 設計 ID: `DS-OP-COMPOSE-ZSCALER-RUNTIME-FT-APPLY-ZSCALER-SETTINGS-RUNTIME`、`DS-OP-LOCAL-IMAGE-NAMES-FT-SEPARATE-PUBLISHED-IMAGE-NAMES`
- 内容: 詳細設計書 9-1 の①〜⑥と、イメージ名のローカル化を `docker-compose.yml` に入れる。
- 完了条件: `docker compose config` が通り、`docker compose config --images` に `ghcr.io` が無い。
- 検証: 上のコマンドと、9 の E2E（ローカル専用のイメージ名）。

## 8. 既存のスクリプトの準備処理の呼び出し

- 設計 ID: `DS-MD-SCRIPTS-BUILD-CLI-EXEC-FT-BUILD-CLI-IMAGES`、`DS-MD-SCRIPTS-SETUP-SH-FT-SETUP-INITIAL-DATA`
- 内容: `scripts/build_cli_exec.sh` を、準備処理のあと compose の定義（`cli_exec_base`・`cli_exec_claude`・`cli_exec_opencode`）でビルドする形に書き換える。`scripts/setup.sh` の最初に準備処理を足す。
- 完了条件: `./scripts/setup.sh` が今と同じ手順で完了し、準備処理は 1 回だけ動く。
- 検証: 9 の E2E（既存の E2E の全件）。

## 9. consumer の Zscaler 設定

- 設計 ID: `DS-MD-ZSCALER-SETTINGS-FT-PASS-ZSCALER-SETTINGS-CLI-CONTAINER`、`DS-CL-ZSCALER-SETTINGS-FT-PASS-ZSCALER-SETTINGS-CLI-CONTAINER`、`DS-FN-LOAD-ZSCALER-SETTINGS-FT-PASS-ZSCALER-SETTINGS-CLI-CONTAINER`、`DS-FN-BUILD-CLI-PROXY-ENV-FT-PASS-ZSCALER-SETTINGS-CLI-CONTAINER`、`DS-FN-BUILD-ZSCALER-INSTRUCTION-FT-INSTRUCT-CLI-ZSCALER`、`DS-FN-APPEND-ZSCALER-INSTRUCTION-FT-INSTRUCT-CLI-ZSCALER`、`DS-FN-MERGE-ZSCALER-CLI-ENV-FT-PASS-ZSCALER-SETTINGS-CLI-CONTAINER`、`DS-MD-CONSUMER-PROMPT-BUILDER-FT-BUILD-PROMPT`、`DS-MD-CONSUMER-CLI-CONTAINER-MANAGER-FT-RUN-CLI-CONTAINER`、`DS-MD-CONSUMER-ENTRY-FT-GRACEFUL-SHUTDOWN`
- 内容: `consumer/zscaler_settings.py` を作り、PromptBuilder（指示文の付加）、CLIContainerManager（環境変数と追加のホスト名）、`consumer/consumer.py`（組み立て）を変える（詳細設計書 4-2-7・5 章）。
- 完了条件: 有効なとき、F-3・F-4 のプロンプトの末尾に指示文が付き、CLI コンテナにプロキシの環境変数と `host.docker.internal` が渡る。無効なときは指示文が付かない。
- 検証: 10 の単体テスト。

## 10. 単体テスト・結合テスト

- 設計 ID: `DS-TS-ZSCALER-UNIT-TESTS-FT-PASS-ZSCALER-SETTINGS-CLI-CONTAINER`、`DS-TS-ZSCALER-SCRIPT-TESTS-FT-REQUIRE-ZSCALER-SETTINGS`、`DS-TS-NO-TLS-VERIFY-DISABLE-NF-TLS-VERIFICATION-ALWAYS-ON`
- 内容: 詳細設計書 8-5 のとおり `tests/consumer/` と `tests/scripts/` に pytest のテストを書く。
- 完了条件: `docker compose --profile test run --rm unit_test` で FAIL が 0 件。
- 検証: 上のコマンド。

## 11. 模擬プロキシとテスト環境セットアップ

- 設計 ID: `DS-OP-ZSCALER-MOCK-COMPOSE-FT-RUN-ZSCALER-MOCK-PROXY`、`DS-FN-START-ZSCALER-MOCK-FT-RUN-ZSCALER-MOCK-PROXY`、`DS-FN-INSTALL-HOST-PYTHON-DEPS-FT-APPLY-ZSCALER-SETTINGS-HOST-SCRIPT`、`DS-IF-TEST-SETUP-ZSCALER-MOCK-UI-TEST-SETUP-ZSCALER-MOCK-OPTION`
- 内容: `zscaler-mock/compose.yaml`（mitmproxy 12.3.1）を作り、`scripts/test_setup.sh` に `--zscaler-mock`、模擬プロキシの起動、ホストの pip への Zscaler 設定の受け渡し、`--run-tests` での `e2e/zscaler/` の実行を足す。
- 完了条件: `./scripts/test_setup.sh --zscaler-mock` が終了コード 0 で終わり、`certs/` と `.env` を書き換えない。
- 検証: 12 の E2E。

## 12. Zscaler の E2E

- 設計 ID: `DS-TS-BUILD-VIA-ZSCALER-MOCK-TS-VERIFY-BUILD-VIA-ZSCALER-MOCK`、`DS-TS-RUNTIME-HTTPS-VIA-ZSCALER-MOCK-TS-VERIFY-RUNTIME-HTTPS-VIA-ZSCALER-MOCK`、`DS-TS-UNTRUSTED-CERT-STOPS-TS-VERIFY-UNTRUSTED-CERT-STOPS`、`DS-TS-MISSING-SETTINGS-STOP-TS-VERIFY-MISSING-SETTINGS-STOP`、`DS-TS-DISABLED-SWITCH-TS-VERIFY-DISABLED-SWITCH`、`DS-TS-OS-BUNDLE-FALLBACK-TS-VERIFY-OS-BUNDLE-FALLBACK`、`DS-TS-MOCK-LLM-E2E-WITH-ZSCALER-TS-VERIFY-MOCK-LLM-E2E-WITH-ZSCALER`、`DS-TS-REAL-LLM-E2E-VIA-MOCK-TS-VERIFY-REAL-LLM-E2E-VIA-MOCK`、`DS-TS-CLI-ZSCALER-INSTRUCTION-TS-VERIFY-CLI-ZSCALER-INSTRUCTION`、`DS-TS-CLI-BROWSER-TRUST-TS-VERIFY-CLI-BROWSER-TRUST`、`DS-TS-CLI-STANDARD-BROWSERS-TS-VERIFY-CLI-STANDARD-BROWSERS`、`DS-TS-REAL-SETTINGS-UNCHANGED-TS-VERIFY-REAL-SETTINGS-UNCHANGED`、`DS-TS-LOCAL-IMAGE-NAMES-TS-VERIFY-LOCAL-IMAGE-NAMES`
- 内容: 詳細設計書 8-2 の Zscaler のシナリオを `e2e/zscaler/` に pytest で書く。
- 完了条件: `./scripts/test_setup.sh --zscaler-mock --run-tests` で全件成功。実 LLM のシナリオは `--real` 付きで手動で 1 回成功させる。
- 検証: 上のコマンド。

## 13. GitHub Actions

- 設計 ID: `DS-OP-LOCAL-IMAGE-NAMES-FT-SEPARATE-PUBLISHED-IMAGE-NAMES`
- 内容: `.github/workflows/build-and-push.yml` に `ZSCALER_ENABLED=false ./scripts/zscaler_prepare.sh` の手順と、各ビルドの `zscaler=.zscaler` のビルドコンテキストを足す。push 先の名前は変えない。
- 完了条件: ワークフローの定義が正しく、ローカルで同じ手順のビルドが通る。
- 検証: `ZSCALER_ENABLED=false ./scripts/zscaler_prepare.sh` のあと、`docker buildx build --build-context zscaler=.zscaler -f backend/Dockerfile .` が成功する。

## 14. 設定の見本・git の管理外・README

- 設計 ID: `DS-OP-GITIGNORE-ZSCALER-DT-ZSCALER-CERT-FILE`、`DS-OP-ENV-EXAMPLE-ZSCALER-NF-EXISTING-ENV-MIGRATION`、`DS-OP-CLI-EXTRA-SETUP-MIGRATION-NF-CLI-EXTRA-SETUP-MIGRATION`、`DS-OP-ZSCALER-SETUP-README-OP-ZSCALER-SETUP-PROCEDURE`
- 内容: `.gitignore` に `certs/`・`.zscaler/`・`zscaler-mock/.data/` を足す。`.env.example` に Zscaler 設定の 3 項目を足す。README に「Zscaler 環境での構築」の節、移行の注意、追加環境のコマンドの apt の書き方を足す。
- 完了条件: README だけで、社内の Linux サーバーでの構築と、社外での `ZSCALER_ENABLED=false` の運用ができる。
- 検証: README の手順を上から読み、9-1・9-2 と食い違いが無いことを確かめる。

---

## 実装完了確認

### 1. 対応表（docs/trace_map.md）更新タスク

- 実装したファイル・クラス・公開関数を `docs/trace_map.md` に登録する。
- 完了条件: `bash scripts/isdd/check.sh --strict` がエラー 0 件・警告 0 件。

### 2. 起動確認タスク

- 実行形態はコンテナ。`./scripts/compose.sh up -d --build` で全サービスが起動することを確かめる（社外では `ZSCALER_ENABLED=false`）。
- 完了条件: 起動がエラーなく完了する。

### 3. 単体テスト・結合テスト全件通過タスク

- `docker compose --profile test run --rm unit_test` で全件を実行する。
- 完了条件: FAIL が 0 件。失敗したら修正と再実行を繰り返す。

### 4. E2E テスト全件通過タスク

- `./scripts/test_setup.sh --run-tests`（Zscaler 設定は無効）と `./scripts/test_setup.sh --zscaler-mock --run-tests` を実行する。外部連携はモックのモード（モック LLM）で行う。
- 完了条件: どちらも FAIL が 0 件。失敗したら修正と再実行を全件通過まで続ける。

### 5. README.md 記載タスク

- README.md の「起動方法」を `./scripts/compose.sh` に合わせ、「初期ユーザー」の節（`./scripts/setup.sh` の引数で作る最初の管理者）を足す（実装完了チェックで現在不足と出ている）。
- 完了条件: README.md を読むだけで初回の起動から初期ログインまでができる。

### 6. 実装完了チェックタスク

- `python3 scripts/isdd/implementation_completeness_checker.py .` を実行する。
- 完了条件: 全項目が OK。

---

## 設計中に直した変更要件（記録）

| 要件 ID | 直した内容 | 理由 | 変更設計への伝播 |
|---|---|---|---|
| `RQ-FT-RUN-STANDARD-BROWSERS-CLI-CONTAINER` | 追加 | Alpine では Playwright の標準のブラウザが起動しないため、ユーザーの選択（理由: 開発するシステムのテストで、Playwright の標準のブラウザの版をそのまま使う必要がある）で CLI コンテナの土台を変える | `DS-OP-CLI-EXEC-UBUNTU-BASE-FT-RUN-STANDARD-BROWSERS-CLI-CONTAINER` ほか |
| `RQ-FT-APPLY-ZSCALER-SETTINGS-CLI-BROWSER` | 対象を Chromium 系と WebKit に絞った | Playwright の Firefox は追加の証明書を信頼させる方法が無く、証明書の検証を無効にしない方針と両立しないため（ユーザー承認 2026-11-01） | `DS-FN-INSTALL-CA-NSS-FT-APPLY-ZSCALER-SETTINGS-CLI-BROWSER` |
| `RQ-TS-VERIFY-CLI-BROWSER-TRUST` | 対象を Chromium と WebKit に直した | 同上 | `DS-TS-CLI-BROWSER-TRUST-TS-VERIFY-CLI-BROWSER-TRUST` |
| `RQ-TS-VERIFY-CLI-STANDARD-BROWSERS` | 追加 | 土台を変えても既存の CLI コンテナの機能が変わらないことを確かめるため | `DS-TS-CLI-STANDARD-BROWSERS-TS-VERIFY-CLI-STANDARD-BROWSERS` |
| `RQ-NF-CLI-EXTRA-SETUP-MIGRATION` | 追加 | 土台が変わり、追加環境の構築コマンド（apk の書き方）が使えなくなるため | `DS-OP-CLI-EXTRA-SETUP-MIGRATION-NF-CLI-EXTRA-SETUP-MIGRATION` |
| `RQ-BZ-SYSTEM-BUILD-OPERATION` | [追加] の行を消し、既存の業務の範囲に Zscaler の準備を加えた | 逆引きで同じ業務が正本にできたため | 変更なし |

確認タスク: 上の各要件が `change_requirements.md` と正本にあり、`change_detail_design.md` の対応する設計 ID に伝わっていることを、`rq_ds_link_checker.py docs/requirements.md docs/detail_design.md` で確かめる（2026-11-01 時点で合格）。

既存の設計要素への対応の追加: `DS-MD-SCRIPTS-TEST-SETUP-SH-FT-SETUP-TEST-ENVIRONMENT`、`DS-MD-SCRIPTS-SETUP-SH-FT-SETUP-INITIAL-DATA`、`DS-MD-SCRIPTS-BUILD-CLI-EXEC-FT-BUILD-CLI-IMAGES`、`DS-MD-CONSUMER-PROMPT-BUILDER-FT-BUILD-PROMPT`、`DS-MD-CONSUMER-CLI-CONTAINER-MANAGER-FT-RUN-CLI-CONTAINER`、`DS-MD-CONSUMER-ENTRY-FT-GRACEFUL-SHUTDOWN` は、逆引きで正本にできた既存のファイルの設計 ID に、今回の要件の対応を足した。削除した旧 CLI コンテナの作りの ID は、正本の `DS-OP-CLI-EXEC-IMAGES-FT-BUILD-CLI-IMAGES` に合わせた。
