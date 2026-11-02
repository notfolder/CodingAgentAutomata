# BACKLOG

## Zscaler 環境対応
概要: .history/2026-11-02-1410-zscaler対応の実装と整合/summary.md

- [ ] PR #10（Zscaler 環境対応）をレビューして main へ取り込む（追加 2026-11-01、重要 高）
- [ ] PR #10 を取り込む前に、既存の環境の運用者へ `.env` に `ZSCALER_ENABLED=false` を書き足すよう知らせる（追加 2026-11-02、重要 高）
- [ ] opencode の実 LLM のシナリオ（T-31・T-32・T-34）を流して通す（追加 2026-11-02、重要 低）
  - `OPENAI_API_KEY` を入れるか、下の「opencode で Claude のモデル」の後に Claude のキーで流す

## opencode で Claude のモデルを使えるようにする

- [ ] isdd-change-req から変更要求として要件・設計を立て、実装する（追加 2026-11-02、重要 低）
  - 要るもの: キーを `ANTHROPIC_API_KEY` で渡す、宛先の末尾に `/v1`、LiteLLM に `claude-haiku-5-5`（詳細: summary.md）

## 既存の不具合

- [ ] 逆引きで見つけた不具合の候補 16 件（`IDEAS.md`）から、直すものを選んで変更要求にする（追加 2026-11-01、重要 高）

## テストの不安定さ

- [ ] Playwright の TS-A-6 がときどき 1 回目に失敗する原因を突き止める（追加 2026-11-01、重要 低）
