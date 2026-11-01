/**
 * ユーザー管理テスト
 * 対象シナリオ: T-01（ユーザー作成）・T-02（Virtual Key更新）・T-03（デフォルトCLI変更）・
 *              T-15（ユーザー削除）・T-17（一般ユーザー自分の詳細閲覧）・
 *              T-18（一般ユーザーが自分のメール/CLIを編集できる）・
 *              T-22（メール重複チェック）
 *
 * 各テストは使うユーザーを自分で作り、終わったら消す（ほかのテストの結果や順番に頼らない）。
 * 消し損ねたテスト用のユーザーは、global-teardown.ts が名前の接頭辞で片付ける。
 */

import { test, expect, type APIRequestContext, type Page } from '@playwright/test';

// テスト用のユーザー名の接頭辞（global-teardown.ts の片付けの対象と合わせる）
const TEST_USER_PREFIX = 'e2e-test-user-';
const DUP_USER_PREFIX = 'e2e-dup-';

const ADMIN_USERNAME = process.env.ADMIN_USERNAME ?? 'admin';
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD ?? 'Admin@123456';
const TEST_USER_PASSWORD = process.env.TEST_USER_PASSWORD ?? 'Test@123456';
const DEFAULT_MODEL = process.env.DEFAULT_CLAUDE_MODEL || 'claude-haiku-4-5-20251001';

// LiteLLM の宛先と Master Key（T-02 で本物の Virtual Key を発行する）
const LITELLM_URL = process.env.LITELLM_URL ?? 'http://litellm:4000';
const LITELLM_MASTER_KEY = process.env.LITELLM_MASTER_KEY ?? 'sk-litellm-master-e2e-test';

// ユーザーの作成は bcrypt（コスト 12）でパスワードをハッシュにするため、
// 前のテストで CLI コンテナなどが CPU を使っていると数秒かかることがある
const CREATE_TIMEOUT_MS = 15000;

// このファイルのテストが作ったユーザーと Virtual Key（afterEach で消す）
const createdUsers: string[] = [];
const createdKeys: string[] = [];

// -----------------------------------------------------------------------
// ヘルパー関数
// -----------------------------------------------------------------------

/**
 * 重ならないテスト用のユーザー名を作る（再試行でも別の名前になる）
 */
function uniqueName(prefix: string): string {
  return `${prefix}${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
}

/**
 * 管理者のアクセストークンを API で取得する
 */
async function adminToken(request: APIRequestContext): Promise<string> {
  const resp = await request.post('/api/auth/login', {
    data: { username: ADMIN_USERNAME, password: ADMIN_PASSWORD },
  });
  expect(resp.status()).toBe(200);
  const body = (await resp.json()) as { access_token: string };
  return body.access_token;
}

/**
 * テスト用のユーザーを API で作る（作ったユーザーは afterEach で消す）
 */
async function createUserViaApi(
  request: APIRequestContext,
  username: string,
  email: string,
): Promise<void> {
  const token = await adminToken(request);
  const resp = await request.post('/api/users', {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      username,
      email,
      password: TEST_USER_PASSWORD,
      virtual_key: 'sk-test-e2e-key',
      default_cli: 'claude',
      default_model: DEFAULT_MODEL,
      role: 'user',
    },
  });
  expect(resp.status()).toBe(201);
  createdUsers.push(username);
}

/**
 * LiteLLM で本物の Virtual Key を発行する（発行したキーは afterEach で消す）
 */
async function generateVirtualKey(request: APIRequestContext): Promise<string> {
  const resp = await request.post(`${LITELLM_URL}/key/generate`, {
    headers: { Authorization: `Bearer ${LITELLM_MASTER_KEY}` },
    data: { models: [DEFAULT_MODEL] },
  });
  expect(resp.status()).toBe(200);
  const key = ((await resp.json()) as { key: string }).key;
  createdKeys.push(key);
  return key;
}

/**
 * ユーザーを API で取得する（ステータスコードと本文を返す）
 */
async function getUserViaApi(
  request: APIRequestContext,
  username: string,
): Promise<{ status: number; body: Record<string, unknown> | null }> {
  const token = await adminToken(request);
  const resp = await request.get(`/api/users/${username}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const body = resp.status() === 200 ? ((await resp.json()) as Record<string, unknown>) : null;
  return { status: resp.status(), body };
}

/**
 * 管理者ログインを行う共通ヘルパー
 */
async function loginAsAdmin(page: Page): Promise<void> {
  await page.goto('/login');
  await page.locator('input[autocomplete="username"]').fill(ADMIN_USERNAME);
  await page.locator('input[autocomplete="current-password"]').fill(ADMIN_PASSWORD);
  await page.locator('[data-testid="login-button"]').click();
  await expect(page).toHaveURL(/\/users/);
}

/**
 * 一般ユーザーログインを行う共通ヘルパー
 */
async function loginAsUser(page: Page, username: string): Promise<void> {
  await page.goto('/login');
  await page.locator('input[autocomplete="username"]').fill(username);
  await page.locator('input[autocomplete="current-password"]').fill(TEST_USER_PASSWORD);
  await page.locator('[data-testid="login-button"]').click();
  await expect(page).toHaveURL(/\/tasks/);
}

/**
 * ユーザー編集画面を開き、保存済みの値が入力欄に読み込まれるまで待つ。
 * 編集画面は開いた後にユーザーを取得して入力欄へ書き込むため、
 * 読み込みより先に打ち込むと、打ち込んだ値が保存済みの値で上書きされる。
 */
async function openEditPage(page: Page, username: string): Promise<void> {
  await page.goto(`/users/${username}/edit`);
  await expect(page.getByLabel('メールアドレス')).not.toHaveValue('');
}

/**
 * ユーザー作成画面の入力欄を埋める
 */
async function fillCreateForm(page: Page, username: string, email: string): Promise<void> {
  await page.goto('/users/new');
  await expect(page.getByRole('heading', { name: 'ユーザー作成' })).toBeVisible();

  // Vuetify の v-text-field は getByLabel で操作する
  await page.getByLabel('ユーザー名 *').fill(username);
  await page.getByLabel('メールアドレス *').fill(email);

  // パスワードフィールドは type="password" で特定
  await page.locator('input[type="password"]').nth(0).fill(TEST_USER_PASSWORD);
  await page.locator('input[type="password"]').nth(1).fill(TEST_USER_PASSWORD);

  await page.getByLabel('Virtual Key *').fill('sk-test-e2e-key');
  await page.getByLabel('デフォルトモデル *').fill(DEFAULT_MODEL);
}

// 各テストが作ったユーザーと Virtual Key を消す（失敗したテストのものも消す）
test.afterEach(async ({ request }) => {
  if (createdKeys.length > 0) {
    await request.post(`${LITELLM_URL}/key/delete`, {
      headers: { Authorization: `Bearer ${LITELLM_MASTER_KEY}` },
      data: { keys: createdKeys.splice(0) },
    });
  }
  if (createdUsers.length === 0) return;
  const token = await adminToken(request);
  while (createdUsers.length > 0) {
    const username = createdUsers.pop() as string;
    await request.delete(`/api/users/${username}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  }
});

// -----------------------------------------------------------------------
// T-01: 管理者がユーザーを作成できる
// -----------------------------------------------------------------------

test('T-01: 管理者が新規ユーザーを登録できる', async ({ page, request }) => {
  const username = uniqueName(TEST_USER_PREFIX);
  const email = `${username}@example.com`;
  // 途中で失敗しても afterEach で消せるよう、先に登録しておく（無ければ削除は 404 で終わる）
  createdUsers.push(username);

  await loginAsAdmin(page);
  await fillCreateForm(page, username, email);

  // 作成ボタンをクリック
  await page.getByRole('button', { name: /作成/ }).click();

  // ユーザー一覧にリダイレクトされる
  await expect(page).toHaveURL(/\/users(?:\/)?$/, { timeout: CREATE_TIMEOUT_MS });

  // 作成したユーザーが登録されている（一覧は 1 画面の件数に限りがあるので、API と詳細画面で確かめる）
  const created = await getUserViaApi(request, username);
  expect(created.status).toBe(200);
  expect(created.body?.email).toBe(email);

  await page.goto(`/users/${username}`);
  await expect(page.locator(`text=${username}`).first()).toBeVisible();
});

// -----------------------------------------------------------------------
// T-02: 管理者がVirtual Keyを更新できる
// -----------------------------------------------------------------------

test('T-02: 管理者がユーザーのVirtual Keyを更新できる', async ({ page, request }) => {
  const username = uniqueName(TEST_USER_PREFIX);
  await createUserViaApi(request, username, `${username}@example.com`);

  await loginAsAdmin(page);

  // ユーザー編集画面へ
  await openEditPage(page, username);

  // Virtual Key フィールドをクリアして、LiteLLM で発行した本物のキーに更新する
  // （保存時に backend が LiteLLM でキーを検証するため、実在しないキーは断られる）
  const newKey = await generateVirtualKey(request);
  const vkInput = page.getByLabel('Virtual Key');
  await vkInput.clear();
  await vkInput.fill(newKey);

  // 保存ボタンクリック
  await page.getByRole('button', { name: /保存/ }).click();

  // 保存に成功するとユーザー詳細画面へ移る（失敗すると編集画面にエラーが出て留まる）
  await expect(page).toHaveURL(new RegExp(`/users/${username}$`), { timeout: 5000 });
});

// -----------------------------------------------------------------------
// T-03: 管理者がデフォルトCLI・モデルを変更できる
// -----------------------------------------------------------------------

test('T-03: 管理者がデフォルトCLI・モデルを変更できる', async ({ page, request }) => {
  const username = uniqueName(TEST_USER_PREFIX);
  await createUserViaApi(request, username, `${username}@example.com`);

  await loginAsAdmin(page);
  await openEditPage(page, username);

  // デフォルトモデル変更
  const modelInput = page.getByLabel('デフォルトモデル');
  await modelInput.clear();
  await modelInput.fill('openai/gpt-4o-mini');

  await page.getByRole('button', { name: /保存/ }).click();
  await expect(page).toHaveURL(new RegExp(`/users/${username}$`), { timeout: 5000 });

  // 変更した値が保存されている
  const saved = await getUserViaApi(request, username);
  expect(saved.status).toBe(200);
  expect(saved.body?.default_model).toBe('openai/gpt-4o-mini');
});

// -----------------------------------------------------------------------
// T-17: 一般ユーザーが自分のユーザー詳細を閲覧できる
// -----------------------------------------------------------------------

test('T-17: 一般ユーザーが自分のユーザー詳細を閲覧できる', async ({ page }) => {
  await loginAsUser(page, 'testuser-opencode');
  await page.goto('/users/testuser-opencode');

  // ユーザー名が表示されている
  await expect(page.locator('text=testuser-opencode').first()).toBeVisible();
  // Virtual Key ラベルが表示される
  await expect(page.locator('text=Virtual Key').first()).toBeVisible();
});

// -----------------------------------------------------------------------
// T-18: 一般ユーザーが自分のメール・デフォルトCLI・モデルを編集できる
// -----------------------------------------------------------------------

test('T-18: 一般ユーザーが自分のメールアドレスを編集できる', async ({ page, request }) => {
  await loginAsUser(page, 'testuser-opencode');
  await openEditPage(page, 'testuser-opencode');

  // 管理者専用フィールド（ロール・ステータス）が非表示であることを確認
  await expect(page.getByLabel('ロール')).not.toBeVisible();

  // メールアドレス変更
  const emailInput = page.getByLabel('メールアドレス');
  await emailInput.clear();
  await emailInput.fill('testuser-opencode-updated@example.com');

  await page.getByRole('button', { name: /保存/ }).click();

  // 保存に成功するとユーザー詳細画面へ移り、変更した値が保存されている
  await expect(page).toHaveURL(/\/users\/testuser-opencode$/, { timeout: 5000 });
  const saved = await getUserViaApi(request, 'testuser-opencode');
  expect(saved.body?.email).toBe('testuser-opencode-updated@example.com');
});

// -----------------------------------------------------------------------
// T-22: 重複メールアドレスでユーザーを登録できない
// -----------------------------------------------------------------------

test('T-22: 同一メールアドレスでユーザーを登録できない', async ({ page, request }) => {
  // 先に、重ねる相手のユーザーを作っておく
  const existing = uniqueName(TEST_USER_PREFIX);
  const existingEmail = `${existing}@example.com`;
  await createUserViaApi(request, existing, existingEmail);

  const duplicateUsername = uniqueName(DUP_USER_PREFIX);
  // 誤って作られた場合も afterEach で消せるよう、先に登録しておく
  createdUsers.push(duplicateUsername);

  await loginAsAdmin(page);
  // 既存ユーザーと同じメールを入力
  await fillCreateForm(page, duplicateUsername, existingEmail);
  await page.getByRole('button', { name: /作成/ }).click();

  // エラーメッセージが表示される
  await expect(page.locator('text=/重複|既に使用|409|email/').first()).toBeVisible({ timeout: CREATE_TIMEOUT_MS });
  // URL は /users/new のまま
  await expect(page).toHaveURL(/\/users\/new/);
  // 重ねたユーザーは作られていない
  expect((await getUserViaApi(request, duplicateUsername)).status).toBe(404);
});

// -----------------------------------------------------------------------
// T-15: ユーザーを削除できる
// -----------------------------------------------------------------------

test('T-15: 管理者がユーザーを削除できる', async ({ page, request }) => {
  const username = uniqueName(TEST_USER_PREFIX);
  await createUserViaApi(request, username, `${username}@example.com`);

  await loginAsAdmin(page);

  // 削除対象ユーザー詳細へ
  await page.goto(`/users/${username}`);

  // 削除ボタンをクリック
  await page.getByRole('button', { name: '削除' }).click();

  // 確認ダイアログが表示される
  await expect(page.locator('text=/削除.*確認|本当に削除|削除しますか/').first()).toBeVisible();

  // 確認ダイアログで実行
  await page.getByRole('button', { name: /削除する|OK|はい/ }).last().click();

  // SC-02 にリダイレクト
  await expect(page).toHaveURL(/\/users(?:\/)?$/);

  // 削除したユーザーが存在しない
  await expect.poll(async () => (await getUserViaApi(request, username)).status, { timeout: 5000 }).toBe(404);
});
