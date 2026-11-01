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

## 4. 管理画面の nginx が backend の名前を要求のたびに引き直す（2026-11-02、正本へ反映済み）

- **見つけたこと**: Zscaler 設定を変えてイメージを作り直すと、backend のイメージだけが変わり、backend のコンテナだけが作り直されて IP アドレスが変わる。frontend の nginx は backend の名前を起動時に 1 回だけ引くため、古い宛先へつなぎ続け、ログインの API が 502 になる（模擬プロキシでの通し確認で起きた）。
- **実装の判断**: `frontend/nginx.conf` で、compose のネットワークの名前解決（`127.0.0.11`）を使い、転送先の名前を要求のたびに引き直す。
- **直した正本の箇所**: 詳細設計書 9-1 の `DS-OP-FRONTEND-SPA-DELIVERY-NF-SCREEN-TRANSITION-2S` の内容に、名前を引き直すことと理由を足した（ユーザーの承認により、実装の前に反映した）。要件の変更は無い。設計 ID の追加・削除は無い。

## 5. E2E のテスト用のユーザーを片付け、各テストを独立させる（2026-11-02、正本へ反映済み）

- **見つけたこと**:
  - `e2e/tests/users.spec.ts` の T-01 は、作ったユーザーを管理画面のユーザー一覧の 1 画面目（10 行）だけで探していた。テストが作ったユーザーは消されずに溜まるので（`gitlab_integration.spec.ts` の `disabled-user-*` は毎回 1 件残る）、約 10 件を超えると毎回失敗した。
  - T-02・T-03・T-22・T-15 は T-01 の作るユーザーに頼っていて、T-01 が落ちるとつられて落ちた。
  - T-02・T-03・T-18 は、保存できたかを「保存」ボタンの文字にも当たる確かめ方で見ていて、保存に失敗しても通っていた。実際には、T-02 は実在しない Virtual Key を入れていて保存が断られていた。T-03 は、編集画面が保存済みの値を読み込む前に打ち込んでいて、打ち込んだ値が上書きされていた。
  - T-01 の作成は、bcrypt でパスワードをハッシュにするため、負荷が高いと 5 秒の待ちを超えることがあった。
- **実装の判断**:
  - 各テストが使うユーザーを API で自分で作り、終わったら消す。
  - 作ったかは一覧ではなく API と詳細画面で確かめる。保存できたかは、詳細画面へ移ったことと、API で読み直した値で確かめる（編集画面は保存に成功するとすぐ詳細画面へ移るので、「保存しました。」は見えない）。
  - 編集画面では、保存済みの値が読み込まれるのを待ってから打ち込む。
  - T-02 は、LiteLLM で本物の Virtual Key を発行して使い、終わったら消す。そのため、Playwright のコンテナに LiteLLM の宛先と Master Key を渡す（`docker-compose.yml`）。
  - 作成の後の待ちを 15 秒にする。
  - `e2e/global-teardown.ts` で、名前の接頭辞（`e2e-test-user-`・`e2e-dup-`・`disabled-user-`）のユーザーを消す。
- **直した正本の箇所**: 詳細設計書 8-4 の E2E の実行の説明に、テスト用のユーザーを消すことと、各テストが独立していることを足した（ユーザーの承認により、実装の前に反映した）。要件の変更、設計 ID の追加・削除は無い。
