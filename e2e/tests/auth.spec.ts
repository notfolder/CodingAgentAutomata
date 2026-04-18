/**
 * 認証・認可テスト
 * 対象シナリオ: T-01（管理者ログイン）・T-21（一般ユーザーがSC-02にアクセス不可）・
 *              T-27（一般ユーザーがSC-07にアクセス不可）・T-19/T-20（他ユーザー詳細/編集不可）
 */

import { test, expect } from '@playwright/test';

// -----------------------------------------------------------------------
// ヘルパー関数
// -----------------------------------------------------------------------

/**
 * ログイン操作を行う共通ヘルパー
 */
async function login(page: import('@playwright/test').Page, username: string, password: string): Promise<void> {
  await page.goto('/login');
  await page.locator('[data-testid="username"]').fill(username);
  await page.locator('[data-testid="password"]').fill(password);
  await page.locator('[data-testid="login-button"]').click();
}

// -----------------------------------------------------------------------
// T-01: 管理者ログインテスト
// -----------------------------------------------------------------------

test('T-01: 管理者が正しい認証情報でログインできる', async ({ page }) => {
  await login(page, 'admin', process.env.ADMIN_PASSWORD ?? 'Admin@123456');
  // 管理者ログイン成功後は /users（ユーザー一覧）に遷移する
  await expect(page).toHaveURL(/\/users/);
});

// -----------------------------------------------------------------------
// ログイン失敗テスト
// -----------------------------------------------------------------------

test('ログイン失敗時にエラーメッセージが表示される', async ({ page }) => {
  await login(page, 'admin', 'wrongpassword');
  // エラーアラートが表示される
  const errorEl = page.locator('[data-testid="error-message"]');
  await expect(errorEl).toBeVisible();
  // URL は /login のまま
  await expect(page).toHaveURL(/\/login/);
});

// -----------------------------------------------------------------------
// 一般ユーザーログインテスト
// -----------------------------------------------------------------------

test('一般ユーザーがログインするとタスク履歴画面に遷移する', async ({ page }) => {
  // テストユーザー（test_setup.py で作成済み）
  await login(page, 'testuser-opencode', process.env.TEST_USER_PASSWORD ?? 'Test@123456');
  // 一般ユーザーは /tasks へ遷移する
  await expect(page).toHaveURL(/\/tasks/);
});

// -----------------------------------------------------------------------
// T-21: 一般ユーザーが SC-02（ユーザー一覧）にアクセスできない
// -----------------------------------------------------------------------

test('T-21: 一般ユーザーがユーザー一覧ページにアクセスできない', async ({ page }) => {
  await login(page, 'testuser-opencode', process.env.TEST_USER_PASSWORD ?? 'Test@123456');
  await expect(page).toHaveURL(/\/tasks/);

  // /users に直接アクセスしようとする
  await page.goto('/users');
  // ユーザー一覧に留まれない（/tasks か / にリダイレクトされる）
  await expect(page).not.toHaveURL(/^.*\/users$/);
});

// -----------------------------------------------------------------------
// T-27: 一般ユーザーが SC-07（システム設定）にアクセスできない
// -----------------------------------------------------------------------

test('T-27: 一般ユーザーがシステム設定ページにアクセスできない', async ({ page }) => {
  await login(page, 'testuser-opencode', process.env.TEST_USER_PASSWORD ?? 'Test@123456');
  await expect(page).toHaveURL(/\/tasks/);

  // /settings に直接アクセスしようとする
  await page.goto('/settings');
  await expect(page).not.toHaveURL(/\/settings/);
});

// -----------------------------------------------------------------------
// T-19: 一般ユーザーが他ユーザーの詳細を閲覧できない
// -----------------------------------------------------------------------

test('T-19: 一般ユーザーが他ユーザーの詳細ページにアクセスできない', async ({ page }) => {
  await login(page, 'testuser-opencode', process.env.TEST_USER_PASSWORD ?? 'Test@123456');
  // 他ユーザーの詳細ページへ直接遷移
  await page.goto('/users/admin');
  // 403エラー相当のメッセージが表示されるか、リダイレクトされる
  const isRedirected = !page.url().includes('/users/admin');
  const hasError = await page.locator('text=/403|権限|アクセス/').isVisible().catch(() => false);
  expect(isRedirected || hasError).toBeTruthy();
});

// -----------------------------------------------------------------------
// T-20: 一般ユーザーが他ユーザーを編集できない
// -----------------------------------------------------------------------

test('T-20: 一般ユーザーが他ユーザーの編集ページにアクセスできない', async ({ page }) => {
  await login(page, 'testuser-opencode', process.env.TEST_USER_PASSWORD ?? 'Test@123456');
  // 他ユーザーの編集ページへ直接遷移
  await page.goto('/users/admin/edit');
  const isRedirected = !page.url().includes('/users/admin/edit');
  const hasError = await page.locator('text=/403|権限|アクセス/').isVisible().catch(() => false);
  expect(isRedirected || hasError).toBeTruthy();
});

// -----------------------------------------------------------------------
// ログアウトテスト
// -----------------------------------------------------------------------

test('ログアウトするとログイン画面に遷移する', async ({ page }) => {
  await login(page, 'admin', process.env.ADMIN_PASSWORD ?? 'Admin@123456');
  await expect(page).toHaveURL(/\/users/);

  // ナビバーのログアウトボタンをクリック
  await page.locator('text=ログアウト').click();
  await expect(page).toHaveURL(/\/login/);
});
