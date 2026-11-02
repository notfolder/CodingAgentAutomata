# CLAUDE

<!-- isdd-setup:begin -->
## isdd トレーサビリティ規則（isdd-setup が管理する。手で編集しない）

- 仕様とコードの対応は `docs/trace_map.md`（対応表）で管理する。コードに要件 ID や設計 ID を書かない。
- クラス・公開関数・ソースファイルを追加、改名、削除したら、同じ作業の中で `docs/trace_map.md` の行を更新する。
- コードを変更した作業の終わりに `bash scripts/isdd/check.sh` を実行する。エラーが出たら直してから作業を終える。警告は報告に含める。
- 設計要素を増やす必要があれば、コードを書く前に `docs/detail_design.md` を更新する。設計 ID の採番は設計スキルの責務で、実装中に ID を作らない。
<!-- isdd-setup:end -->

## このプロジェクトの決まり

- **外へ出る通信は、必ず Zscaler の証明書を信頼したうえでプロキシを経由させる。証明書の検証を無効にしない。**
- **起動は `./scripts/compose.sh`、テスト環境は `./scripts/test_setup.sh`（模擬プロキシは `--zscaler-mock`）を使う。`docker compose` を直接使わない。**
- **Zscaler まわりを変えたら、模擬プロキシありと `ZSCALER_ENABLED=false` の両方の通し確認で確かめる。**
