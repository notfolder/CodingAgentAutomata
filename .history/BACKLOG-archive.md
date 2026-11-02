# BACKLOG-archive

## Zscaler 環境対応

- [x] (2026-11-01) 既存コードの isdd 化（正本 `docs/requirements.md`・`docs/detail_design.md` と対応表 `docs/trace_map.md`）と、Zscaler の変更の要件・設計の正本への反映
- [x] (2026-11-02) tasks.md の実装（`19522ca`）と、模擬プロキシあり・Zscaler 設定を無効・実 LLM での確認
- [x] (2026-11-02) 実装後の逆引き整合（`docs/proposals.md` を正本へ反映して削除、`f607f49`）

## テストの不安定さ

- [x] (2026-11-02) users の E2E を独立させ、保存の失敗を見逃さないようにする（`24b3759`、詳細設計書 8-4）
- [x] (2026-11-02) 管理画面の nginx が backend の名前を要求のたびに引き直すようにする（`2c33ec0`、詳細設計書 9-1）
