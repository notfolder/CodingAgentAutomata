# BACKLOG

## 本番の GitLab の URL と opencode のタイトル用のモデル

- [ ] 変更要件（`.history/20261103-gitlab-url-and-opencode-small-model/change_requirements.md`）を確定し、設計・実装する（追加 2026-11-03、重要 高）
  - 起動の構成が GitLab の URL をテスト用に固定している問題（IDEAS の候補 12）と、opencode の OpenAI の経路のタイトル用のモデルの 400 を直す。ブランチ `feature/gitlab-url-and-opencode-small-model`

## opencode で Claude のモデルを使えるようにする
概要: .history/2026-11-03-1405-opencodeでClaudeモデル/summary.md

- [ ] opencode の実 LLM のシナリオ（T-31・T-32・T-34）を流して通す（追加 2026-11-02、重要 低）
  - 2026-11-03 に Claude（Haiku）で T-31・T-32 は通過。T-34 は「T-33・T-34 の差分の確認が早すぎる」で落ちる

## 既存の不具合

- [ ] 逆引きで見つけた不具合の候補 16 件（`IDEAS.md`）から、直すものを選んで変更要求にする（追加 2026-11-01、重要 高）

## テストの不安定さ

- [ ] Playwright の TS-A-6 がときどき 1 回目に失敗する原因を突き止める（追加 2026-11-01、重要 低）
- [ ] T-33・T-34 の差分の確認が早すぎる。途中経過のコメントに「Hello from Docker!」が出た直後、プッシュより前に MR の差分を見て落ちることがある（追加 2026-11-03、重要 低）
  - 2026-11-03 の実 LLM の確認で T-34 が 2 回とも落ちたが、後で見ると差分に `docker-compose.yml` が入っていた
