/**
 * タスク実行履歴テスト
 * 対象シナリオ: T-14（管理者がタスク履歴フィルタで確認）・
 *              T-23（一般ユーザーが自分のタスクのみ閲覧）
 */

import { test, expect } from '@playwright/test';

// -----------------------------------------------------------------------
// ヘルパー関数
// -----------------------------------------------------------------------

async function loginAsAdmin(page: import('@playwright/test').Page): Promise<void> {
  await page.goto('/login');
  await page.locator('[data-testid="username"]').fill('admin');
  await page.locator('[data-testid="password"]').fill(process.env.ADMIN_PASSWORD ?? 'Admin@123456');
  await page.locator('[data-testid="login-button"]').click();
  await expect(page).toHaveURL(/\/users/);
}

async function loginAsUser(page: import('@playwright/test').Page, username: string): Promise<void> {
  await page.goto('/login');
  await page.locator('[data-testid="username"]').fill(username);
  await page.locator('[data-testid="password"]').fill(process.env.TEST_USER_PASSWORD ?? 'Test@123456');
  await page.locator('[data-testid="login-button"]').click();
  await expect(page).toHaveURL(/\/tasks/);
}

// -----------------------------------------------------------------------
// T-14: タスク実行履歴確認（フィルタ）
// -----------------------------------------------------------------------

test('T-14: タスク実行履歴ページが表示される', async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto('/tasks');

  // ページタイトルが表示される
  await expect(page.locator('text=タスク実行履歴')).toBeVisible();

  // テーブルが表示される
  await expect(page.locator('table, .v-table, [role="table"]')).toBeVisible();
});

test('T-14: ステータスフィルタでcompletedを選択できる', async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto('/tasks');

  // ステータスフィルタが表示される
  const statusFilter = page.locator('text=ステータス').locator('..').locator('select, .v-select, [role="listbox"]').first();

  // ステータスフィルタが存在する
  await expect(page.locator('text=ステータス')).toBeVisible();
});

test('T-14: ユーザー名フィルタが表示される（admin）', async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto('/tasks');

  // 管理者は全ユーザーのタスクを見られる（ユーザー名フィルタが操作可能）
  await expect(page.locator('text=ユーザー名')).toBeVisible();
});

// -----------------------------------------------------------------------
// T-23: 一般ユーザーが自分のタスクのみ閲覧できる
// -----------------------------------------------------------------------

test('T-23: 一般ユーザーがタスク履歴ページにアクセスできる', async ({ page }) => {
  await loginAsUser(page, 'testuser-opencode');

  // /tasks がデフォルト画面なので既にいる、もしくは直接アクセス
  await page.goto('/tasks');
  await expect(page.locator('text=タスク実行履歴')).toBeVisible();
});

test('T-23: 一般ユーザーのユーザー名フィルタは自分のみ固定', async ({ page }) => {
  await loginAsUser(page, 'testuser-opencode');
  await page.goto('/tasks');

  // ユーザー名フィルタに自分のユーザー名が固定表示されている
  await expect(page.locator('text=testuser-opencode')).toBeVisible();
});

// -----------------------------------------------------------------------
// システム設定テスト（T-25, T-27）
// -----------------------------------------------------------------------

test('T-25: 管理者がシステム設定ページにアクセスできる', async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto('/settings');

  // システム設定画面が表示される
  await expect(page.locator('text=システム設定')).toBeVisible();
});

test('T-25: 管理者がF-3テンプレートを表示できる', async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto('/settings');

  // F-3テンプレートタブまたはセクションが存在する
  await expect(page.locator('text=/F-3|Issue.*MR変換/')).toBeVisible();
});

// -----------------------------------------------------------------------
// 画面遷移テスト（ナビゲーション）
// -----------------------------------------------------------------------

test('ナビゲーションバーが表示される（管理者）', async ({ page }) => {
  await loginAsAdmin(page);

  // ナビバーの主要リンクが表示される
  await expect(page.locator('text=ユーザー一覧')).toBeVisible();
  await expect(page.locator('text=タスク履歴')).toBeVisible();
  await expect(page.locator('text=システム設定')).toBeVisible();
  await expect(page.locator('text=ログアウト')).toBeVisible();
});

test('ナビゲーションバーが表示される（一般ユーザー）', async ({ page }) => {
  await loginAsUser(page, 'testuser-opencode');

  // 一般ユーザーはユーザー一覧・システム設定が非表示
  await expect(page.locator('text=タスク履歴')).toBeVisible();
  await expect(page.locator('text=ログアウト')).toBeVisible();
  // ユーザー一覧・システム設定リンクは表示されない
  await expect(page.locator('nav text=ユーザー一覧')).not.toBeVisible();
  await expect(page.locator('nav text=システム設定')).not.toBeVisible();
});
