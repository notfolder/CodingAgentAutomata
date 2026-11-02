# Zscaler 環境対応の実装・確認・正本の整合と PR #10
更新: 2026-11-02 14:10 JST
セッション: b26d43f6-44ad-450d-a9b5-20488076bfcb
ログ: ./session.md

## 概要
Zscaler（明示型プロキシ・TLS の中身を確かめる方式）の下でビルド・運用できるよう実装し、模擬プロキシあり・無効・実 LLM で確かめ、正本を整合させて PR #10 を作った。

## やったこと

- **依頼**: graph-mcp-gateway を参考に、Zscaler 内でも構築・利用できるようにする。外へ出るときは必ず Zscaler の証明書を使う。Zscaler の役をする模擬プロキシも作る。
- **isdd の流れ**: 既存コードの isdd 化（正本と対応表）→ 変更要件定義 → 変更詳細設計 → tasks.md の実装 → 実装後の逆引き整合。成果物は `.history/20261101-zscaler-support/` と `docs/`。
- **実装**（ブランチ `feature/zscaler-support`、PR #10、コミット 5 件）
  - `.env` の `ZSCALER_*` と `certs/zscaler-ca.pem` から生成物 `.zscaler/` を作る準備処理（`scripts/lib/zscaler.sh`、`scripts/compose.sh`）。
  - 全イメージで証明書を OS の信頼先に入れる（`scripts/zscaler/install-ca.sh`）。実行中の部品にプロキシの環境変数と証明書を渡す。
  - CLI コンテナの土台を Ubuntu 24.04 の共通イメージ（`cli-exec/base`）にし、Playwright の標準のブラウザ（Chromium 系と WebKit）が動くようにした。consumer が CLI コンテナへプロキシの環境変数と指示文を渡す。
  - mitmproxy の模擬プロキシ（`zscaler-mock/`）と `./scripts/test_setup.sh --zscaler-mock`。単体テスト 23 件（`tests/`）と Zscaler の E2E 15 シナリオ（`e2e/zscaler/`）。
- **確認の途中で見つけて直したこと**
  - 管理画面の nginx が backend の名前を起動時に 1 回だけ引いていて、backend だけが作り直されるとログインが 502 になった。要求のたびに引き直すようにした。
  - users の E2E が、テスト用のユーザーが溜まると失敗し、保存の失敗（実在しない Virtual Key、読み込み前の入力）も見逃していた。各テストが自分のユーザーを作って消す形にし、テストの終わりにテスト用のユーザーを片付けるようにした。
  - Zscaler の E2E の標準のブラウザの確認に、開き直しを足した（OrbStack では、ブラウザを取得した直後の数十秒、外への最初の接続が詰まる）。
- **確認の結果**（2026-11-02）
  - 模擬プロキシでの通し確認: Playwright 62 件通過（再試行なし）・2 件スキップ、Zscaler の E2E 11 件通過・4 件スキップ。
  - Zscaler 設定を無効にした通し確認: Playwright 62 件通過・2 件スキップ、Zscaler の E2E 5 件通過・10 件スキップ。
  - 実 LLM: Zscaler の E2E 12 件通過。opencode のシナリオ（T-31・T-32・T-34）は `OPENAI_API_KEY` が空のため確かめていない。
  - `check.sh --strict`・`rq_ds_link_checker.py`・`implementation_completeness_checker.py` はすべて問題 0 件。
- **実装後の逆引き整合**: 実装中の提案 5 件を正本へ反映し、`docs/proposals.md` を削除した。`RQ-TS-VERIFY-CLI-ZSCALER-INSTRUCTION` の確かめ方を実装に合わせ、CLI コンテナの証明書と OS の束の確認を E2E に足した。
- **意図的に残したもの**: opencode の実 LLM のシナリオ、opencode で Claude のモデルを使えるようにする件、逆引きで見つけた既存の不具合の候補 16 件（`IDEAS.md`）。

## 決定事項

- 外へ出る通信は、必ず Zscaler の証明書を信頼したうえでプロキシを経由させる（社内の開発環境・本番環境ともに Zscaler 配下のため）。
- Zscaler は明示型プロキシで、プロキシの認証は無い。`ZSCALER_ENABLED` の既定は有効で、使わない環境は `.env` に `ZSCALER_ENABLED=false` を書く。
- 証明書は `certs/zscaler-ca.pem` に置き、無ければホストの OS の証明書の束を使う。
- CLI コンテナの土台は Ubuntu（社内では Ubuntu が主流のため）。Playwright の標準のブラウザの版をそのまま使う（開発するシステムのテストで要るため）。Firefox は Playwright で独自の認証局を信頼させられないので対象外。
- 確かめる範囲に実 LLM を含める（本番環境でも構築・運用できる必要があるため）。opencode の実 LLM のシナリオは、今回は流し直さない（Zscaler の変更は 2 つの CLI で同じため）。
- 依存の無い問いは、番号を付けてまとめて聞く。
- テストの直しは PR #10 に含める。正本の整合も PR #10 に含める。

## 次にやること

1. PR #10 をレビューして main へ取り込む。取り込む前に、既存の環境の運用者へ `ZSCALER_ENABLED=false` の書き足しを知らせる。
2. 必要なら、opencode で Claude のモデルを使えるようにする件を `isdd-change-req` から始める。
3. 逆引きで見つけた不具合の候補（`IDEAS.md`）から、直すものを選んで変更要求にする。

## バックログ

- [ ] PR #10（Zscaler 環境対応）をレビューして main へ取り込む（追加 2026-11-01、重要 高）
- [ ] PR #10 を取り込む前に、既存の環境の運用者へ `.env` に `ZSCALER_ENABLED=false` を書き足すよう知らせる（追加 2026-11-02、重要 高）
- [ ] opencode の実 LLM のシナリオ（T-31・T-32・T-34）を流して通す（追加 2026-11-02、重要 低）
- [ ] opencode で Claude のモデルを使えるようにする（isdd-change-req から）（追加 2026-11-02、重要 低）
- [ ] 逆引きで見つけた不具合の候補 16 件から、直すものを選んで変更要求にする（追加 2026-11-01、重要 高）
- [ ] Playwright の TS-A-6 がときどき 1 回目に失敗する原因を突き止める（追加 2026-11-01、重要 低）
- [x] (2026-11-01) 既存コードの isdd 化と、Zscaler の変更の要件・設計の正本への反映
- [x] (2026-11-02) tasks.md の実装、模擬プロキシあり・無効・実 LLM での確認
- [x] (2026-11-02) 管理画面の nginx の名前の引き直し
- [x] (2026-11-02) users の E2E を独立させ、保存の失敗を見逃さないようにする
- [x] (2026-11-02) 実装後の逆引き整合（`docs/proposals.md` を正本へ反映して削除）
