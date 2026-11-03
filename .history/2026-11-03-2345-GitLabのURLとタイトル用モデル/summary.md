# 本番の GitLab の URL と opencode のタイトル用のモデル（PR #13）

更新: 2026-11-03 23:45 JST
セッション: 545956de-1e18-4fcd-8281-99f1a5d5eedb
ログ: ./session.md

## 概要

compose が GitLab の URL をテスト用に固定する問題と、opencode の OpenAI の経路のタイトル用のモデルの 400 を isdd で仕様化・実装・正本へ反映し、T-35 の不安定さの直しも含めて PR #13 にした（レビュー待ち）。

## やったこと

- PR #12 の取り込みを確かめて main に戻り、作業ブランチ `feature/gitlab-url-and-opencode-small-model` を作った。PR #12 のバックログの項目を完了にした。
- isdd-spec（変更フロー）で要件・設計・tasks.md を作った（`.history/20261103-gitlab-url-and-opencode-small-model/`）。
  - 業務課題: 本番では `.env` の GitLab の URL を手直し無しで使う。どのプロバイダでも opencode のタイトル用のモデルに本体のモデルを使い、異常でないエラーを無くす。
- isdd-build で実装し、正本（`docs/requirements.md`・`docs/detail_design.md`・`docs/trace_map.md`）へ反映した。
  - `docker-compose.yml` から `GITLAB_API_URL` の固定を外した。テスト環境の構築は `.env.test` にコンテナから見た `http://gitlab:8929` を書き、ホストからは `http://localhost:8929` を使う。`.env` は書き換えない。
  - `CLIAdapterResolver.build_opencode_provider_config` が、どのプロバイダでも `small_model` に本体のモデルを入れる。
  - ホストの E2E（`e2e/zscaler/test_runtime_settings_e2e.py`）: GitLab の URL、`.env` を書き換えないこと、LiteLLM Proxy に無いモデルの呼び出し 0 件。T-36（opencode で Claude のモデルを使う Issue→MR 変換）を追加。
  - isdd を v2.1.0 に更新した。
- 変更前に T-31 だけを流し、LiteLLM Proxy のログに `Invalid model name passed in model=gpt-5.4-nano` が出ることを確かめた（設計書の想定 `gpt-5.4-nano-flex` とは名前が違った）。
- 実装中に見つけた設計の前提の誤り 2 件を、正本の設計書に直接反映した。
  - Issue→MR 変換のタスクには CLI とモデルが記録されないので、T-36 では確かめない。
  - T-31・T-32 は DB に残ったデフォルトモデルを使うので、テストの最初にモデルを決める。
- レビュー中の追加の直し（PR #13 に追加）。
  - 実 LLM モードの T-31・T-32 は `DEFAULT_CLAUDE_MODEL` を使う（OpenAI の API キーが無くても流せる）。
  - T-35 の `TypeError: fetch failed`（`SocketError: other side closed`）: E2E の API の呼び出しを `apiFetch` にまとめ、読み取りの要求だけ 1 回やり直し、失敗に URL を出す。`waitUntil` は例外で落とさない。接続をわざと切るサーバーで、やり直しが働くことを確かめた（確認用のコードはコミットしていない）。
- E2E: `ZSCALER_ENABLED=false` で全件 3 回、模擬プロキシありで全件 1 回、実 LLM モードで T-31・T-32・T-35・T-36 を 2 回。すべて通過。
- 意図的に残したもの
  - T-35 が実際に落ちた状況（GitLab が重いときの切断）そのものは再現していない。
  - 追加の直しの後は、模擬プロキシありの全件を流し直していない（Zscaler まわりではないため）。
  - isdd のチェッカーが、対応だけを差し替えた設計 ID を「削除する設計 ID」とみなす不具合は、ユーザーが別に直している。
- 環境メモ: テスト環境はモック LLM モード（`ZSCALER_ENABLED=false`）の状態。手元の `.env` には OpenAI の API キーが無く、Anthropic の API キーだけがある。テスト環境の DB のパスワードは `.env.example` の既定値のまま。

## 決定事項

- A（GitLab の URL）と D（タイトル用のモデル）を 1 つの変更にする（ユーザーの選択）。
- 本番の `.env` を本番の値に書き換えるのは前提の作業で、手直しには数えない（ユーザー）。
- テスト環境の構築は冪等にする。`.env.test` は毎回作り直してよい（ユーザー）。
- タイトル用のモデルが直ったことは、LiteLLM Proxy への無いモデルの呼び出しが 0 件であることを E2E で確かめる。変更したら確かめるのは当たり前（ユーザー）。
- Claude の経路の Issue→MR 変換も E2E で確かめる（T-36。ユーザーの選択）。
- 実 LLM モードの T-31・T-32 は Claude のモデルで流す（ユーザーの選択）。
- T-35 の直しは、API の呼び出しをまとめて読み取りだけやり直し、URL を出す方式。PR #13 に含める（ユーザー）。

## 次にやること

- PR #13 をレビューして main へ取り込む。取り込む前に、本番の運用者へ compose の `GITLAB_API_URL` の手直しを戻すよう知らせる。
- 取り込んだら main に戻り、ローカルとリモートの作業ブランチを片付ける（リモートの削除は自動許可モードで止まるので、ユーザーに `!` で実行してもらう）。

## バックログ

- [ ] PR #13 をレビューして main へ取り込む（追加 2026-11-03、重要 高）
- [ ] opencode の実 LLM のシナリオ（T-31・T-32・T-34）を流して通す（追加 2026-11-02、重要 低）。T-31・T-32 は実 LLM モードで通過。T-34 は OpenAI の API キーが要る
- [ ] 逆引きで見つけた不具合の候補の残り 15 件から、直すものを選んで変更要求にする（追加 2026-11-01、重要 高）
- [x] (2026-11-03) PR #12 をレビューして main へ取り込む
- [x] (2026-11-03) 実 LLM モードの T-35 がときどき `fetch failed` で落ちる問題を直す（PR #13）
