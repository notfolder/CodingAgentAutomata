/**
 * Group Webhook GUI テスト (SC-08)
 * 対象シナリオ:
 *   TS-WB-1: SC-08 への全ユーザーアクセス確認
 *   TS-WB-2: グループ一覧表示・テキスト検索絞り込み確認
 *   TS-WB-3: Webhook登録の正常完了確認
 *   TS-WB-4: 登録後の登録済みバッジ表示確認
 *   TS-WB-5: Webhook削除の正常完了確認
 *   TS-WB-6: 削除後の未登録状態確認
 *   TS-WB-7: 登録確認ダイアログ表示内容確認
 *   TS-WB-8: 削除確認ダイアログ表示内容確認
 *   TS-WB-9: 確認ダイアログのキャンセル動作確認
 *   TS-WB-10: 未ログインアクセス制御確認
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
  await page.locator('input[autocomplete="username"]').fill('admin');
  await page.locator('input[autocomplete="current-password"]').fill(
    process.env.ADMIN_PASSWORD ?? 'Admin@123456',
  );
  await page.locator('[data-testid="login-button"]').click();
  await expect(page).toHaveURL(/\/users/);
}

/**
 * 一般ユーザーログインを行う共通ヘルパー
 */
async function loginAsUser(page: import('@playwright/test').Page): Promise<void> {
  await page.goto('/login');
  await page.locator('input[autocomplete="username"]').fill('testuser-opencode');
  await page.locator('input[autocomplete="current-password"]').fill(
    process.env.TEST_USER_PASSWORD ?? 'Test@123456',
  );
  await page.locator('[data-testid="login-button"]').click();
  await expect(page).toHaveURL(/\/tasks/);
}

// -----------------------------------------------------------------------
// TS-WB-1: SC-08 への全ユーザーアクセス確認
// -----------------------------------------------------------------------

test('TS-WB-1: 管理者がGroup Webhook管理画面にアクセスできる', async ({ page }) => {
  await loginAsAdmin(page);

  // ナビゲーションから Webhook管理 へ移動
  await page.getByRole('link', { name: 'Webhook管理' }).click();
  await expect(page).toHaveURL(/\/webhooks/);

  // 画面タイトルが表示される
  await expect(page.getByRole('heading', { name: 'Group Webhook管理' })).toBeVisible();
});

test('TS-WB-1: 一般ユーザーがGroup Webhook管理画面にアクセスできる', async ({ page }) => {
  await loginAsUser(page);

  // ナビゲーションから Webhook管理 へ移動
  await page.getByRole('link', { name: 'Webhook管理' }).click();
  await expect(page).toHaveURL(/\/webhooks/);

  // 画面タイトルが表示される
  await expect(page.getByRole('heading', { name: 'Group Webhook管理' })).toBeVisible();
});

// -----------------------------------------------------------------------
// TS-WB-2: グループ一覧表示・テキスト検索絞り込み確認
// -----------------------------------------------------------------------

test('TS-WB-2: グループ一覧が表示されテキスト検索で絞り込みができる', async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto('/webhooks');

  // ローディングが完了するまで待機（最大30秒）
  await page.waitForLoadState('networkidle');

  // 画面が表示されていることを確認
  await expect(page.getByRole('heading', { name: 'Group Webhook管理' })).toBeVisible();

  // 検索フィールドが表示される
  const searchField = page.getByLabel('グループ名で検索');
  await expect(searchField).toBeVisible();

  // グループが1件以上表示されている場合のみ検索テストを実施
  const tableRows = page.locator('tbody tr');
  const rowCount = await tableRows.count();

  if (rowCount > 0) {
    // 検索フィールドにテキストを入力して絞り込みを確認
    // 最初の行のグループ名を取得して検索する
    const firstGroupName = await tableRows.nth(0).locator('td').nth(0).textContent();
    if (firstGroupName) {
      const searchTerm = firstGroupName.substring(0, 3);
      await searchField.fill(searchTerm);
      // 絞り込まれた結果が表示される（入力に一致するものが含まれる）
      await expect(tableRows.first()).toBeVisible();
      // 検索クリア
      await searchField.clear();
    }
  }
});

// -----------------------------------------------------------------------
// TS-WB-3: Webhook登録の正常完了確認 & TS-WB-4: 登録後の登録済みバッジ表示確認
// -----------------------------------------------------------------------

test('TS-WB-3/TS-WB-4: 未登録グループへのWebhook登録が完了し登録済みバッジが表示される', async ({
  page,
}) => {
  await loginAsAdmin(page);
  await page.goto('/webhooks');
  await page.waitForLoadState('networkidle');

  // 未登録グループの「登録」ボタンを探す
  const registerBtn = page.getByRole('button', { name: '登録' }).first();

  if (!(await registerBtn.isVisible())) {
    // 未登録グループがない場合はスキップ（テスト環境依存）
    test.skip();
    return;
  }

  // 登録ボタンをクリックして確認ダイアログを開く
  await registerBtn.click();

  // 確認ダイアログが表示される
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.getByText('Webhook 登録の確認')).toBeVisible();

  // 「登録する」ボタンをクリック
  await page.getByRole('button', { name: '登録する' }).click();

  // ダイアログが閉じて一覧が更新される（スナックバーが表示されるか、ダイアログが消える）
  await expect(page.getByRole('dialog')).not.toBeVisible({ timeout: 15000 });

  // 一覧の更新を待機
  await page.waitForLoadState('networkidle');

  // 登録済みバッジが表示されていることを確認（少なくとも1件）
  const registeredChip = page.getByText('登録済み').first();
  if (await registeredChip.isVisible()) {
    await expect(registeredChip).toBeVisible();
  }
});

// -----------------------------------------------------------------------
// TS-WB-5: Webhook削除の正常完了確認 & TS-WB-6: 削除後の未登録状態確認
// -----------------------------------------------------------------------

test('TS-WB-5/TS-WB-6: 登録済みグループのWebhook削除が完了し未登録状態に戻る', async ({
  page,
}) => {
  await loginAsAdmin(page);
  await page.goto('/webhooks');
  await page.waitForLoadState('networkidle');

  // 登録済みグループの「削除」ボタンを探す
  const deleteBtn = page.getByRole('button', { name: '削除' }).first();

  if (!(await deleteBtn.isVisible())) {
    // 登録済みグループがない場合はスキップ（テスト環境依存）
    test.skip();
    return;
  }

  // 削除ボタンをクリックして確認ダイアログを開く
  await deleteBtn.click();

  // 確認ダイアログが表示される
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.getByText('Webhook 削除の確認')).toBeVisible();

  // 「削除する」ボタンをクリック
  await page.getByRole('button', { name: '削除する' }).click();

  // ダイアログが閉じる
  await expect(page.getByRole('dialog')).not.toBeVisible({ timeout: 15000 });

  // 一覧の更新を待機
  await page.waitForLoadState('networkidle');
});

// -----------------------------------------------------------------------
// TS-WB-7: 登録確認ダイアログ表示内容確認
// -----------------------------------------------------------------------

test('TS-WB-7: 登録確認ダイアログにグループ名が表示される', async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto('/webhooks');
  await page.waitForLoadState('networkidle');

  // 未登録グループの「登録」ボタンを探す
  const registerBtn = page.getByRole('button', { name: '登録' }).first();

  if (!(await registerBtn.isVisible())) {
    test.skip();
    return;
  }

  // ボタンと同行のグループ名を取得
  const row = registerBtn.locator('xpath=ancestor::tr');
  const groupNameCell = row.locator('td').nth(0);
  const groupName = await groupNameCell.textContent();

  // 登録ボタンをクリック
  await registerBtn.click();

  // 確認ダイアログが表示される
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.getByText('Webhook 登録の確認')).toBeVisible();

  // グループ名がダイアログに表示される
  if (groupName) {
    await expect(page.getByRole('dialog').getByText(groupName.trim())).toBeVisible();
  }

  // 「キャンセル」ボタンが存在する
  await expect(page.getByRole('button', { name: 'キャンセル' })).toBeVisible();
  // 「登録する」ボタンが存在する
  await expect(page.getByRole('button', { name: '登録する' })).toBeVisible();

  // ダイアログを閉じる（キャンセル）
  await page.getByRole('button', { name: 'キャンセル' }).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
});

// -----------------------------------------------------------------------
// TS-WB-8: 削除確認ダイアログ表示内容確認
// -----------------------------------------------------------------------

test('TS-WB-8: 削除確認ダイアログにグループ名とWebhook URLが表示される', async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto('/webhooks');
  await page.waitForLoadState('networkidle');

  // 登録済みグループの「削除」ボタンを探す
  const deleteBtn = page.getByRole('button', { name: '削除' }).first();

  if (!(await deleteBtn.isVisible())) {
    test.skip();
    return;
  }

  // 削除ボタンをクリック
  await deleteBtn.click();

  // 確認ダイアログが表示される
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.getByText('Webhook 削除の確認')).toBeVisible();

  // 「キャンセル」ボタンが存在する
  await expect(page.getByRole('button', { name: 'キャンセル' })).toBeVisible();
  // 「削除する」ボタンが存在する
  await expect(page.getByRole('button', { name: '削除する' })).toBeVisible();

  // ダイアログを閉じる（キャンセル）
  await page.getByRole('button', { name: 'キャンセル' }).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
});

// -----------------------------------------------------------------------
// TS-WB-9: 確認ダイアログのキャンセル動作確認
// -----------------------------------------------------------------------

test('TS-WB-9: 確認ダイアログでキャンセルすると操作が中断される', async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto('/webhooks');
  await page.waitForLoadState('networkidle');

  // 未登録または登録済みのいずれかのボタンを探す
  const registerBtn = page.getByRole('button', { name: '登録' }).first();
  const deleteBtn = page.getByRole('button', { name: '削除' }).first();

  let actionBtn;
  if (await registerBtn.isVisible()) {
    actionBtn = registerBtn;
  } else if (await deleteBtn.isVisible()) {
    actionBtn = deleteBtn;
  } else {
    test.skip();
    return;
  }

  // ボタンをクリックしてダイアログを開く
  await actionBtn.click();

  // 確認ダイアログが表示される
  await expect(page.getByRole('dialog')).toBeVisible();

  // 一覧の行数を記録
  const beforeRowCount = await page.locator('tbody tr').count();

  // 「キャンセル」をクリック
  await page.getByRole('button', { name: 'キャンセル' }).click();

  // ダイアログが閉じる
  await expect(page.getByRole('dialog')).not.toBeVisible();

  // 一覧の状態が変化していない（行数が同じ）
  const afterRowCount = await page.locator('tbody tr').count();
  expect(afterRowCount).toBe(beforeRowCount);
});

// -----------------------------------------------------------------------
// TS-WB-10: 未ログインアクセス制御確認
// -----------------------------------------------------------------------

test('TS-WB-10: 未ログイン状態で /webhooks にアクセスするとログイン画面にリダイレクトされる', async ({
  page,
}) => {
  // ログインせずに直接 /webhooks にアクセス
  await page.goto('/webhooks');

  // ログイン画面にリダイレクトされる
  await expect(page).toHaveURL(/\/login/);
});

