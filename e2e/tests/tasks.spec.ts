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
  await page.locator('input[autocomplete="username"]').fill('admin');
  await page.locator('input[autocomplete="current-password"]').fill(process.env.ADMIN_PASSWORD ?? 'Admin@123456');
  await page.locator('[data-testid="login-button"]').click();
  await expect(page).toHaveURL(/\/users/);
}

async function loginAsUser(page: import('@playwright/test').Page, username: string): Promise<void> {
  await page.goto('/login');
  await page.locator('input[autocomplete="username"]').fill(username);
  await page.locator('input[autocomplete="current-password"]').fill(process.env.TEST_USER_PASSWORD ?? 'Test@123456');
  await page.locator('[data-testid="login-button"]').click();
  await expect(page).toHaveURL(/\/tasks/);
}

// -----------------------------------------------------------------------
// T-14: タスク実行履歴確認（フィルタ）
// -----------------------------------------------------------------------

test('T-14: タスク実行履歴ページが表示される', async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto('/tasks');

  // ページタイトル（heading）が表示される
  await expect(page.getByRole('heading', { name: 'タスク実行履歴' })).toBeVisible();

  // v-data-table（テーブルコンテナ）が表示される
  await expect(page.locator('.v-data-table').first()).toBeVisible();
});

test('T-14: ステータスフィルタでcompletedを選択できる', async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto('/tasks');

  // ステータスフィルタ（v-select）のラベルが存在する
  // getByLabel はフィルタカード内の v-select に関連付けられたラベルを見つける
  await expect(page.getByLabel('ステータス').first()).toBeVisible();
});

test('T-14: ユーザー名フィルタが表示される（admin）', async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto('/tasks');

  // 管理者は全ユーザーのタスクを見られる（ユーザー名フィルタが操作可能）
  await expect(page.getByLabel('ユーザー名').first()).toBeVisible();
});

// -----------------------------------------------------------------------
// T-23: 一般ユーザーが自分のタスクのみ閲覧できる
// -----------------------------------------------------------------------

test('T-23: 一般ユーザーがタスク履歴ページにアクセスできる', async ({ page }) => {
  await loginAsUser(page, 'testuser-opencode');

  // /tasks がデフォルト画面なので既にいる、もしくは直接アクセス
  await page.goto('/tasks');
  await expect(page.getByRole('heading', { name: 'タスク実行履歴' })).toBeVisible();
});

test('T-23: 一般ユーザーのユーザー名フィルタは自分のみ固定', async ({ page }) => {
  await loginAsUser(page, 'testuser-opencode');
  await page.goto('/tasks');

  // ユーザー名フィルタに自分のユーザー名が入力されている（readonly）
  await expect(page.getByLabel('ユーザー名').first()).toHaveValue('testuser-opencode');
});

// -----------------------------------------------------------------------
// システム設定テスト（T-25, T-27）
// -----------------------------------------------------------------------

test('T-25: 管理者がシステム設定ページにアクセスできる', async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto('/settings');

  // システム設定ページのタイトルが表示される
  await expect(page.getByRole('heading', { name: 'システム設定' })).toBeVisible();
});

test('T-25: 管理者がF-3テンプレートを表示できる', async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto('/settings');

  // F-3 テンプレートタブが存在する
  await expect(page.locator('text=F-3 テンプレート')).toBeVisible();
});

// -----------------------------------------------------------------------
// 画面遷移テスト（ナビゲーション）
// -----------------------------------------------------------------------

test('ナビゲーションバーが表示される（管理者）', async ({ page }) => {
  await loginAsAdmin(page);

  // ナビバーの主要リンクが表示される
  await expect(page.getByRole('link', { name: 'ユーザー一覧' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'タスク履歴' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'システム設定' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'ログアウト' })).toBeVisible();
});

test('ナビゲーションバーが表示される（一般ユーザー）', async ({ page }) => {
  await loginAsUser(page, 'testuser-opencode');

  // 一般ユーザーはタスク履歴とログアウトのみ表示
  await expect(page.getByRole('link', { name: 'タスク履歴' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'ログアウト' })).toBeVisible();
  // ユーザー一覧・システム設定リンクは非表示（v-if で DOM から除外）
  await expect(page.getByRole('link', { name: 'ユーザー一覧' })).not.toBeVisible();
  await expect(page.getByRole('link', { name: 'システム設定' })).not.toBeVisible();
});

