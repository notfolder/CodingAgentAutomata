# GitHub Copilot CLI 認証・ヘッドレス実行 調査メモ

## 1. PAT（Personal Access Token）による認証

SSOを使わずに他のデバイスへ認証を展開する方法として、**Fine-grained PAT** が利用可能。

> ⚠️ **Classic PAT（`ghp_` プレフィックス）は非対応。** Fine-grained PAT のみサポート。

### 手順

1. https://github.com/settings/personal-access-tokens/new にアクセス
2. **"Copilot Requests"** パーミッションを追加して生成
3. 以下の環境変数に設定（優先順位順）：

```bash
export COPILOT_GITHUB_TOKEN=github_pat_xxxxxxxxxxxx  # 最優先
export GH_TOKEN=github_pat_xxxxxxxxxxxx
export GITHUB_TOKEN=github_pat_xxxxxxxxxxxx
```

`.env` ファイルへの記載例：

```env
COPILOT_GITHUB_TOKEN=github_pat_xxxxxxxxxxxx
```

```bash
source .env && copilot
```

### 注意事項

- PATは個人アカウントに紐付くため、**1人1トークン**が原則
- `.env` は必ず `.gitignore` に追加してリポジトリにコミットしないこと
- Copilotサブスクリプションが有効なアカウントのトークンが必要

---

## 2. ヘッドレスモード（非インタラクティブ実行）

### 基本的な起動方法（ファイルからプロンプトを読み込む）

プロンプトはファイルに書き出し、**パイプで標準入力として渡す**のが推奨。
`--autopilot` を付けることでユーザー確認なしにタスクを完遂する。
`-p` フラグは短いプロンプト向けで、長い・複数行のプロンプトには不向き。

```bash
# 基本形：ファイルからプロンプトを読み込んで実行
cat prompt.txt | copilot --autopilot --allow-all -s

# エージェント指定と組み合わせ
cat prompt.txt | copilot --autopilot --agent=task-agent --allow-all -s
```

`-s` / `--silent` フラグを付けるとエージェントの応答のみ出力されスクリプト向きになる。

### プロンプトファイルの書き方

```
# prompt.txt
src/main.py のバグを修正してください。

以下の条件を満たすこと：
- 既存のテストがすべてパスすること
- 変更は最小限にとどめること
```

ヒアドキュメントでも渡せる：

```bash
copilot --allow-all -s << 'EOF'
src/main.py のバグを修正してください。
既存のテストがすべてパスするようにしてください。
EOF
```

> ℹ️ `-p -` や `-p /dev/stdin` はパイプ記法として機能しない（`-` がそのままプロンプト文字列になる）。
> パイプは `-p` フラグなしで直接渡す。
>
> 参考：[Issue #1046 - Allow prompts to be passed via stdin](https://github.com/github/copilot-cli/issues/1046)（2026年1月 動作確認・Close済み）

### フラグ一覧

| フラグ / 環境変数 | 効果 |
|--------|------|
| `cat prompt.txt \| copilot` | **ファイルからプロンプトを読み込む（推奨）** |
| `-p` / `--prompt <text>` | 短いプロンプトを引数で渡す（非インタラクティブ・実行後終了） |
| `-i` / `--interactive <prompt>` | インタラクティブモードで起動し、指定プロンプトを自動実行 |
| `-s` / `--silent` | エージェントの応答のみ出力（スクリプト向き） |
| `--allow-all` / `--yolo` | ファイル変更・コマンド実行の確認をすべてスキップ |
| `--allow-all-tools` / `COPILOT_ALLOW_ALL` | ツール実行の確認のみスキップ（環境変数でも設定可） |
| `--autopilot` | Autopilotモードで起動（`Shift+Tab` 不要） |
| `--experimental` | 実験的機能へのアクセスを有効化（Autopilot自動起動ではない） |

### Autopilotモードについて

- **`--autopilot` フラグ**でCLI起動時からAutopilotモードを有効化できる（`Shift+Tab` 不要）
- `--experimental` は実験的機能へのアクセスを有効にするだけで、Autopilotを自動起動するわけではない

### セキュリティ上の注意

`--allow-all` / `--yolo` はすべてのファイル操作・コマンド実行を**無条件で許可**するため、使用は以下の環境に限定することを推奨：

- CI/CDパイプライン
- 検証済みの信頼できるローカル環境

---

## 参考

- [GitHub Copilot CLI 公式ドキュメント](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/use-copilot-cli)
- [Copilot CLI インストール](https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli)
