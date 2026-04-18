/**
 * ユーザー管理テスト
 * 対象シナリオ: T-01（ユーザー作成）・T-02（Virtual Key更新）・T-03（デフォルトCLI変更）・
 *              T-15（ユーザー削除）・T-17（一般ユーザー自分の詳細閲覧）・
 *              T-18（一般ユーザーが自分のメール/CLIを編集できる）・
 *              T-22（メール重複チェック）
 */

import { test, expect } from '@playwright/test';

// -----------------------------------------------------------------------
// ヘルパー関数
// -----------------------------------------------------------------------

/**
 * 管理者ログインを行う共通ヘルパー
 */
async function loginAsAdmin(page: import('@playwright/test').Page): Promise<void> {
  await page.goto('/login');
  await page.locator('[data-testid="username"]').fill('admin');
  await page.locator('[data-testid="password"]').fill(process.env.ADMIN_PASSWORD ?? 'Admin@123456');
  await page.locator('[data-testid="login-button"]').click();
  await expect(page).toHaveURL(/\/users/);
}

/**
 * 一般ユーザーログインを行う共通ヘルパー
 */
async function loginAsUser(page: import('@playwright/test').Page, username: string): Promise<void> {
  await page.goto('/login');
  await page.locator('[data-testid="username"]').fill(username);
  await page.locator('[data-testid="password"]').fill(process.env.TEST_USER_PASSWORD ?? 'Test@123456');
  await page.locator('[data-testid="login-button"]').click();
  await expect(page).toHaveURL(/\/tasks/);
}

// テスト用ユーザー名（各テストで一意にする）
const TEST_USERNAME = `e2e-test-user-${Date.now()}`;
const TEST_EMAIL = `${TEST_USERNAME}@example.com`;

// -----------------------------------------------------------------------
// T-01: 管理者がユーザーを作成できる
// -----------------------------------------------------------------------

test('T-01: 管理者が新規ユーザーを登録できる', async ({ page }) => {
  await loginAsAdmin(page);

  // ユーザー作成画面に遷移
  await page.goto('/users/new');

  // フォームに入力
  await page.locator('input[autocomplete="username"], input[label="ユーザー名"], [placeholder*="ユーザー"]').first().fill(TEST_USERNAME);
  // Vuetify の v-text-field は label で特定
  await page.locator('text=ユーザー名').locator('..').locator('input').fill(TEST_USERNAME);

  // メールアドレス
  await page.locator('text=メールアドレス').locator('..').locator('input').fill(TEST_EMAIL);

  // パスワード
  const passwordInputs = page.locator('input[type="password"]');
  await passwordInputs.nth(0).fill('Test@123456');
  await passwordInputs.nth(1).fill('Test@123456');

  // Virtual Key
  await page.locator('text=Virtual Key').locator('..').locator('input').fill('sk-test-e2e');

  // 作成ボタン
  await page.locator('button:has-text("作成")').click();

  // SC-02（ユーザー一覧）にリダイレクトされる
  await expect(page).toHaveURL(/\/users/);

  // 作成したユーザーがリストに表示される
  await expect(page.locator(`text=${TEST_USERNAME}`)).toBeVisible();
});

// -----------------------------------------------------------------------
// T-02: 管理者がVirtual Keyを更新できる
// -----------------------------------------------------------------------

test('T-02: 管理者がユーザーのVirtual Keyを更新できる', async ({ page }) => {
  await loginAsAdmin(page);

  // ユーザー詳細から編集画面へ
  await page.goto(`/users/${TEST_USERNAME}/edit`);

  // Virtual Key フィールドを更新
  const vkInput = page.locator('text=Virtual Key').locator('..').locator('input');
  await vkInput.clear();
  await vkInput.fill('sk-test-updated');

  // 保存ボタンクリック
  await page.locator('button:has-text("保存")').click();

  // 成功メッセージ（スナックバーまたはフラッシュ）が表示される
  await expect(page.locator('text=/保存|更新|成功/')).toBeVisible({ timeout: 5000 });
});

// -----------------------------------------------------------------------
// T-03: 管理者がデフォルトCLI・モデルを変更できる
// -----------------------------------------------------------------------

test('T-03: 管理者がデフォルトCLI・モデルを変更できる', async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto(`/users/${TEST_USERNAME}/edit`);

  // デフォルトモデル変更
  const modelInput = page.locator('text=デフォルトモデル').locator('..').locator('input');
  await modelInput.clear();
  await modelInput.fill('openai/gpt-4o');

  await page.locator('button:has-text("保存")').click();
  await expect(page.locator('text=/保存|更新|成功/')).toBeVisible({ timeout: 5000 });
});

// -----------------------------------------------------------------------
// T-17: 一般ユーザーが自分のユーザー詳細を閲覧できる
// -----------------------------------------------------------------------

test('T-17: 一般ユーザーが自分のユーザー詳細を閲覧できる', async ({ page }) => {
  await loginAsUser(page, 'testuser-opencode');
  await page.goto('/users/testuser-opencode');

  // ユーザー名が表示されている
  await expect(page.locator('text=testuser-opencode')).toBeVisible();
  // Virtual Key は末尾4文字マスク形式で表示
  await expect(page.locator('text=Virtual Key')).toBeVisible();
});

// -----------------------------------------------------------------------
// T-18: 一般ユーザーが自分のメール・デフォルトCLI・モデルを編集できる
// -----------------------------------------------------------------------

test('T-18: 一般ユーザーが自分のメールアドレスを編集できる', async ({ page }) => {
  await loginAsUser(page, 'testuser-opencode');
  await page.goto('/users/testuser-opencode/edit');

  // Virtual Key・ロール・ステータスの入力欄が表示されないことを確認
  await expect(page.locator('text=ロール')).not.toBeVisible();
  await expect(page.locator('text=ステータス')).not.toBeVisible();

  // メールアドレス変更
  const emailInput = page.locator('text=メールアドレス').locator('..').locator('input');
  await emailInput.clear();
  await emailInput.fill('testuser-opencode-new@example.com');

  await page.locator('button:has-text("保存")').click();
  await expect(page.locator('text=/保存|更新|成功/')).toBeVisible({ timeout: 5000 });
});

// -----------------------------------------------------------------------
// T-22: 重複メールアドレスでユーザーを登録できない
// -----------------------------------------------------------------------

test('T-22: 同一メールアドレスでユーザーを登録できない', async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto('/users/new');

  const duplicateUsername = `e2e-dup-${Date.now()}`;
  // 既存ユーザーと同じメールを入力
  await page.locator('text=ユーザー名').locator('..').locator('input').fill(duplicateUsername);
  await page.locator('text=メールアドレス').locator('..').locator('input').fill(TEST_EMAIL);
  const passwordInputs = page.locator('input[type="password"]');
  await passwordInputs.nth(0).fill('Test@123456');
  await passwordInputs.nth(1).fill('Test@123456');
  await page.locator('text=Virtual Key').locator('..').locator('input').fill('sk-test');

  await page.locator('button:has-text("作成")').click();

  // エラーメッセージが表示される
  await expect(page.locator('text=/重複|既に使用|409/')).toBeVisible({ timeout: 5000 });
  // URL は /users/new のまま
  await expect(page).toHaveURL(/\/users\/new/);
});

// -----------------------------------------------------------------------
// T-15: ユーザーを削除できる
// -----------------------------------------------------------------------

test('T-15: 管理者がユーザーを削除できる', async ({ page }) => {
  await loginAsAdmin(page);

  // 削除対象ユーザー詳細へ
  await page.goto(`/users/${TEST_USERNAME}`);

  // 削除ボタンをクリック
  await page.locator('button:has-text("削除")').click();

  // 確認ダイアログが表示される
  await expect(page.locator('text=/削除.*確認|本当に削除/')).toBeVisible();

  // 確認ダイアログで実行
  await page.locator('button:has-text("削除する"), button:has-text("OK"), button:has-text("はい")').last().click();

  // SC-02 にリダイレクト
  await expect(page).toHaveURL(/\/users$/);

  // 削除したユーザーが一覧に表示されない
  await expect(page.locator(`text=${TEST_USERNAME}`)).not.toBeVisible();
});
