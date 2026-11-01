# 実装中に見つけた設計の不足・矛盾（isdd-post-implementation-review で正本へ反映する）

## 1. ビルドのホストネットワークをやめる（Zscaler 環境対応、2026-11-01）

- **見つけたこと**: docker compose v5.5 は、ビルドの `network: host` に追加の許可（`--allow=network.host`）を求め、`docker compose build` からは渡せないため、ビルドが止まる。古い組み立て方に戻す `COMPOSE_BAKE=false` も効かない。既存の backend・frontend・producer・consumer のビルドも `network: host` を指定していたため、今の版では元からビルドできない。
- **実装の判断**:
  - すべてのビルドから `network: host` を外し、ビルドに追加のホスト名 `host.docker.internal:host-gateway` を付けた。
  - 模擬プロキシのビルド用の宛先を `http://host.docker.internal:18080`（実行中の部品と同じ）にした。
  - ホストで行う使用前の接続確認と、テスト環境セットアップのホストの pip は `http://127.0.0.1:18080` を使う。生成物の `build.env` に `ZSCALER_HOST_PROXY` を足した。本物の Zscaler では 3 つとも `ZSCALER_PROXY_URL` と同じ。
- **直す正本の箇所**: 詳細設計書の 2-5-4（ネットワーク構成図の説明）、3-1 の `DS-SC-ZSCALER-GENERATED-DIR-FT-RESOLVE-CERT-BUNDLE`（`build.env` の項目）、4-2-5（模擬の宛先）、4-2-6（「すべてのビルドはホストネットワークで行う」の記述）、9-1 の `DS-OP-COMPOSE-ZSCALER-RUNTIME-FT-APPLY-ZSCALER-SETTINGS-RUNTIME`（①のホストネットワーク）。設計 ID の追加・削除は無い。

## 2. Zscaler の E2E を、Zscaler 設定が無効のときも実行する（2026-11-01）

- **見つけたこと**: 詳細設計書 8-4 は「`--zscaler-mock` のときは `e2e/zscaler/` の pytest も実行する」としているが、無効のスイッチのシナリオ（`DS-TS-DISABLED-SWITCH-TS-VERIFY-DISABLED-SWITCH`）と標準のブラウザのシナリオ（`DS-TS-CLI-STANDARD-BROWSERS-TS-VERIFY-CLI-STANDARD-BROWSERS`）は、Zscaler 設定が無効のときにしか確かめられない。
- **実装の判断**: `--run-tests` では、模擬プロキシの有無によらず `e2e/zscaler/` を実行する。各シナリオは生成物の状態（`.zscaler/state`）と模擬プロキシの起動の有無で、実行するかを決める。
- **直す正本の箇所**: 詳細設計書 8-4 の `--run-tests` の説明、8-3 の Zscaler の E2E の説明。

## 3. Zscaler の E2E の確かめ方の具体化（2026-11-01）

- 無効のスイッチのシナリオは、consumer のコンテナの中で、CLI へ渡す環境変数と指示文が無効の値になっていることで確かめる（タスクを流してプロンプトを取り出す仕組みが無いため）。
- 指示文のシナリオは、consumer のコンテナの中で、DB のシステム設定のテンプレートとユーザー個別のテンプレートの両方から作ったプロンプトの末尾を確かめる。
- Node.js の fetch の確認では、`NODE_USE_ENV_PROXY=1` を付ける（Node.js の fetch は既定ではプロキシの環境変数を読まないため）。
- **直す正本の箇所**: 詳細設計書 8-2 の該当するシナリオの手順。
