# 要件整合確認レポート: LiteLLM Proxy（opencode から Claude のモデルを呼ぶ）

確認日: 2026-11-02

## 1. 入力した要件

- 変更要件定義書 `.history/20261102-opencode-claude-model/change_requirements.md`
- 外部仕様の調査結果 `external/litellm/docs/research.md`

## 2. 一致している要件

| RQ-ID | 要件名 | 外部仕様との対応 |
|---|---|---|
| `RQ-FT-CALL-CLAUDE-VIA-OPENCODE` | opencode での Claude のモデルの呼び出し | LiteLLM Proxy の `/v1/messages` で、Virtual Key を使って Claude のモデルを呼べる（Opus 5.5 と Haiku 4.5 で確認）。タイトル用のモデルは設定の `small_model` で本体と同じものにできる |
| `RQ-FT-DETERMINE-OPENCODE-PROVIDER` | opencode のプロバイダの判定 | opencode のモデル名の `anthropic/` は、opencode の Anthropic 用の呼び方に対応する。`openai/` の呼び方は、宛先に `/v1` を付けても付けなくても動く |
| `RQ-NF-OPENCODE-CLAUDE-NO-MIGRATION` | 既存の環境での移行作業の不要 | Virtual Key を設定の JSON の中で渡せるので、CLI アダプタ設定の書き換えは要らない |
| `RQ-TS-VERIFY-OPENCODE-CLAUDE-MODEL` | opencode での Claude のモデルの MR 処理 | モック LLM モードでは LiteLLM Proxy の `drop_params` を有効にすれば通る。実 LLM モードは Anthropic の API キーだけで通る |
| `RQ-EF-SOFT-SAVING-OPENCODE-CLAUDE` | 見込み経営効果 | 外部仕様に関係しない |

## 3. 不整合な要件

| 種類 | 内容 | 対象 |
|---|---|---|
| 不足 | 変更要件定義書の「3-3. 外部連携」に、モックの方式の行が無かった。opencode で Claude のモデルを指定したシナリオを、モック LLM モードで流すためのモックの扱いが要件に書かれていない | 変更要件定義書 3-3 |
| 矛盾 | 無い | – |
| 過剰 | 無い | – |

範囲外で見つかったこと（要件の不整合ではない）: 既存の OpenAI の経路では、opencode のタイトル用のモデルが LiteLLM Proxy に無く、400 になってから呼び直している。処理は完了する。`.history/IDEAS.md` に記録した。

## 4. 修正方針

- 「3-3. 外部連携」に、ローカルの HTTP サーバー方式のモック（既存のモック LLM を LiteLLM Proxy の転送先にし、モック LLM が応じない設定項目を LiteLLM Proxy が捨てる）の行を追加する。対応する業務課題は、opencode での Claude のモデルの利用と、自動での動作確認とする。
- 「3-3. 外部連携」の本文に、opencode が Claude のモデルを Anthropic の形式で呼ぶことを書く（呼び方の選定の結果）。
- 業務課題と要件の対応表に、追加した行を反映する。

（ユーザーの確認: 2026-11-02、修正方針どおりに反映することを了承）

## 5. 修正後の確認結果

- 変更要件定義書に上の修正を反映した。
- 要件 ID の整合チェック（`rq_integrity_checker.py`）は問題 0 件。
- 修正後の要件と外部仕様に、不足・矛盾・過剰は無い。

## 6. 設計に進めるかの判定

**進める。** 未解消の不整合は無い。設計では次を前提にする。

- opencode の Anthropic 用の呼び方を使い、宛先は LiteLLM Proxy の URL に `/v1` を付けたものにする。
- Virtual Key は opencode に渡す設定の JSON の中で渡し、CLI アダプタ設定は変えない。
- タイトル用のモデルには、本体と同じモデルを指定する。
- モック LLM モードの LiteLLM Proxy の設定で、モック LLM が応じない設定項目を捨てる。
