# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: users.spec.ts >> T-15: 管理者がユーザーを削除できる
- Location: tests/users.spec.ts:175:5

# Error details

```
Test timeout of 60000ms exceeded.
```

```
Error: locator.click: Test timeout of 60000ms exceeded.
Call log:
  - waiting for getByRole('button', { name: '削除' })

```

# Page snapshot

```yaml
- generic [ref=e4]:
  - banner [ref=e5]:
    - generic [ref=e6]:
      - generic [ref=e8]: CodingAgentAutomata
      - link "ユーザー一覧" [ref=e9] [cursor=pointer]:
        - /url: /users
        - generic [ref=e10]:
          - generic [ref=e11]: 󰡉
          - text: ユーザー一覧
      - link "タスク履歴" [ref=e12] [cursor=pointer]:
        - /url: /tasks
        - generic [ref=e13]:
          - generic [ref=e14]: 󱃔
          - text: タスク履歴
      - link "システム設定" [ref=e15] [cursor=pointer]:
        - /url: /settings
        - generic [ref=e16]:
          - generic [ref=e17]: 󰒓
          - text: システム設定
      - button "ログアウト" [ref=e18] [cursor=pointer]:
        - generic [ref=e19]:
          - generic [ref=e20]: 󰍃
          - text: ログアウト
  - main [ref=e21]:
    - generic [ref=e22]:
      - generic [ref=e24]:
        - button "戻る" [ref=e25] [cursor=pointer]:
          - generic [ref=e27]: 󰁍
          - generic [ref=e28]: 戻る
        - heading "ユーザー詳細" [level=1] [ref=e29]:
          - generic [ref=e30]: 󰀄
          - text: ユーザー詳細
      - alert [ref=e31]:
        - generic [ref=e33]: 󰅙
        - generic [ref=e34]: ユーザーが見つかりません。
```

# Test source

```ts
  82  | 
  83  |   // Virtual Key フィールドをクリアして更新
  84  |   const vkInput = page.getByLabel('Virtual Key');
  85  |   await vkInput.clear();
  86  |   await vkInput.fill('sk-test-updated-key');
  87  | 
  88  |   // 保存ボタンクリック
  89  |   await page.getByRole('button', { name: '保存' }).click();
  90  | 
  91  |   // 成功スナックバーが表示される
  92  |   await expect(page.locator('text=/保存|更新|成功/').first()).toBeVisible({ timeout: 5000 });
  93  | });
  94  | 
  95  | // -----------------------------------------------------------------------
  96  | // T-03: 管理者がデフォルトCLI・モデルを変更できる
  97  | // -----------------------------------------------------------------------
  98  | 
  99  | test('T-03: 管理者がデフォルトCLI・モデルを変更できる', async ({ page }) => {
  100 |   await loginAsAdmin(page);
  101 |   await page.goto(`/users/${TEST_USERNAME}/edit`);
  102 | 
  103 |   // デフォルトモデル変更
  104 |   const modelInput = page.getByLabel('デフォルトモデル');
  105 |   await modelInput.clear();
  106 |   await modelInput.fill('openai/gpt-4o');
  107 | 
  108 |   await page.getByRole('button', { name: '保存' }).click();
  109 |   await expect(page.locator('text=/保存|更新|成功/').first()).toBeVisible({ timeout: 5000 });
  110 | });
  111 | 
  112 | // -----------------------------------------------------------------------
  113 | // T-17: 一般ユーザーが自分のユーザー詳細を閲覧できる
  114 | // -----------------------------------------------------------------------
  115 | 
  116 | test('T-17: 一般ユーザーが自分のユーザー詳細を閲覧できる', async ({ page }) => {
  117 |   await loginAsUser(page, 'testuser-opencode');
  118 |   await page.goto('/users/testuser-opencode');
  119 | 
  120 |   // ユーザー名が表示されている
  121 |   await expect(page.locator('text=testuser-opencode').first()).toBeVisible();
  122 |   // Virtual Key ラベルが表示される
  123 |   await expect(page.locator('text=Virtual Key').first()).toBeVisible();
  124 | });
  125 | 
  126 | // -----------------------------------------------------------------------
  127 | // T-18: 一般ユーザーが自分のメール・デフォルトCLI・モデルを編集できる
  128 | // -----------------------------------------------------------------------
  129 | 
  130 | test('T-18: 一般ユーザーが自分のメールアドレスを編集できる', async ({ page }) => {
  131 |   await loginAsUser(page, 'testuser-opencode');
  132 |   await page.goto('/users/testuser-opencode/edit');
  133 | 
  134 |   // 管理者専用フィールド（ロール・ステータス）が非表示であることを確認
  135 |   await expect(page.getByLabel('ロール')).not.toBeVisible();
  136 | 
  137 |   // メールアドレス変更
  138 |   const emailInput = page.getByLabel('メールアドレス');
  139 |   await emailInput.clear();
  140 |   await emailInput.fill('testuser-opencode-updated@example.com');
  141 | 
  142 |   await page.getByRole('button', { name: '保存' }).click();
  143 |   await expect(page.locator('text=/保存|更新|成功/').first()).toBeVisible({ timeout: 5000 });
  144 | });
  145 | 
  146 | // -----------------------------------------------------------------------
  147 | // T-22: 重複メールアドレスでユーザーを登録できない
  148 | // -----------------------------------------------------------------------
  149 | 
  150 | test('T-22: 同一メールアドレスでユーザーを登録できない', async ({ page }) => {
  151 |   await loginAsAdmin(page);
  152 |   await page.goto('/users/new');
  153 | 
  154 |   const duplicateUsername = `e2e-dup-${Date.now()}`;
  155 |   // 既存ユーザーと同じメールを入力
  156 |   await page.getByLabel('ユーザー名 *').fill(duplicateUsername);
  157 |   await page.getByLabel('メールアドレス *').fill(TEST_EMAIL);
  158 |   await page.locator('input[type="password"]').nth(0).fill('Test@123456');
  159 |   await page.locator('input[type="password"]').nth(1).fill('Test@123456');
  160 |   await page.getByLabel('Virtual Key *').fill('sk-test');
  161 |   await page.getByLabel('デフォルトモデル *').fill('claude-opus-4-5');
  162 | 
  163 |   await page.getByRole('button', { name: '作成' }).click();
  164 | 
  165 |   // エラーメッセージが表示される
  166 |   await expect(page.locator('text=/重複|既に使用|409|email/').first()).toBeVisible({ timeout: 5000 });
  167 |   // URL は /users/new のまま
  168 |   await expect(page).toHaveURL(/\/users\/new/);
  169 | });
  170 | 
  171 | // -----------------------------------------------------------------------
  172 | // T-15: ユーザーを削除できる
  173 | // -----------------------------------------------------------------------
  174 | 
  175 | test('T-15: 管理者がユーザーを削除できる', async ({ page }) => {
  176 |   await loginAsAdmin(page);
  177 | 
  178 |   // 削除対象ユーザー詳細へ
  179 |   await page.goto(`/users/${TEST_USERNAME}`);
  180 | 
  181 |   // 削除ボタンをクリック
> 182 |   await page.getByRole('button', { name: '削除' }).click();
      |                                                  ^ Error: locator.click: Test timeout of 60000ms exceeded.
  183 | 
  184 |   // 確認ダイアログが表示される
  185 |   await expect(page.locator('text=/削除.*確認|本当に削除|削除しますか/')).toBeVisible();
  186 | 
  187 |   // 確認ダイアログで実行
  188 |   await page.getByRole('button', { name: /削除する|OK|はい/ }).last().click();
  189 | 
  190 |   // SC-02 にリダイレクト
  191 |   await expect(page).toHaveURL(/\/users(?:\/)?$/);
  192 | 
  193 |   // 削除したユーザーが一覧に表示されない
  194 |   await expect(page.locator(`text=${TEST_USERNAME}`).first()).not.toBeVisible({ timeout: 5000 });
  195 | });
  196 | 
  197 | 
```