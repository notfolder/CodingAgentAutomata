/**
 * GitLab 統合 E2E テスト
 *
 * 対象シナリオ:
 *   T-04: Issue を Webhook で検出して MR 変換
 *   T-05: Issue をポーリングで MR 変換
 *   T-06: MR 変換後に bot アサイン・ラベルが引き継がれる
 *   T-07: MR の CLI 処理が実行される
 *   T-08: MR description の CLI 指定でデフォルトを上書き
 *   T-09: MR レビュアーが未設定の場合は MR 作成者の Virtual Key が使われる
 *   T-10: 未登録ユーザーの Issue は処理されない
 *   T-11: bot アサインのみでは処理されない（ラベルなし）
 *   T-12: ラベルのみでは処理されない（bot アサインなし）
 *   T-13: 無効化ユーザーの Issue は処理されない
 *   T-24: Webhook とポーリングが同時検出しても重複処理されない
 *   T-28: MR 処理中に CLI 出力が進捗コメントに定期更新される
 *   T-30: MR 処理中に bot のアサインが解除されたら CLI が強制終了する
 *   T-31: testuser-opencode の Issue を opencode CLI で MR 変換できる
 *   T-32: testuser-opencode の MR を opencode CLI で処理できる
 *
 * 前提条件:
 *   - docker compose --profile test up -d で GitLab CE が起動済み
 *   - GITLAB_API_URL 環境変数に GitLab の URL（例: http://localhost:8929）
 *   - GITLAB_ADMIN_TOKEN 環境変数に GitLab 管理者 PAT
 *   - GITLAB_BOT_LABEL 環境変数にトリガーラベル名（デフォルト: "coding agent"）
 *   - GITLAB_BOT_NAME 環境変数に bot のユーザー名（デフォルト: "coding-agent-bot"）
 *   - GITLAB_PROJECT_ID 環境変数にテスト用プロジェクト ID
 *   - BACKEND_URL 環境変数に Backend の URL（デフォルト: http://localhost:8000）
 */

import { test, expect, request as playwrightRequest } from '@playwright/test';

// -----------------------------------------------------------------------
// 設定定数（環境変数から取得）
// -----------------------------------------------------------------------

const GITLAB_API_URL = process.env.GITLAB_API_URL ?? 'http://localhost:8929';
const GITLAB_ADMIN_TOKEN = process.env.GITLAB_ADMIN_TOKEN ?? '';
// テストユーザー（testuser-claude）の GitLab PAT。Issue 作成者として backend の users テーブルに存在するユーザーを使う
const GITLAB_USER_TOKEN = process.env.GITLAB_USER_TOKEN ?? '';
// テストユーザー（testuser-opencode）の GitLab PAT。opencode CLI テスト用
const GITLAB_USER_TOKEN_OPENCODE = process.env.GITLAB_USER_TOKEN_OPENCODE ?? '';
const GITLAB_BOT_NAME = process.env.GITLAB_BOT_NAME ?? 'coding-agent-bot';
const GITLAB_BOT_LABEL = process.env.GITLAB_BOT_LABEL ?? 'coding agent';
const GITLAB_PROJECT_ID = process.env.GITLAB_PROJECT_ID ?? '';
const BACKEND_URL = process.env.BACKEND_URL ?? 'http://localhost:8000';
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD ?? 'Admin@123456';

// タイムアウト設定（GitLab 統合テストは時間がかかる）
const TASK_TIMEOUT_MS = 120_000;  // タスク処理完了待ち最大120秒
const POLLING_INTERVAL_MS = 3_000;  // ポーリング間隔3秒

// -----------------------------------------------------------------------
// GitLab API ヘルパー
// -----------------------------------------------------------------------

/**
 * GitLab REST API を呼び出す共通ヘルパー
 */
async function gitlabApi(
  method: string,
  path: string,
  token: string,
  body?: Record<string, unknown>
): Promise<{ status: number; data: unknown }> {
  const url = `${GITLAB_API_URL}/api/v4${path}`;
  const headers: Record<string, string> = {
    'PRIVATE-TOKEN': token,
    'Content-Type': 'application/json',
  };
  const options: RequestInit = { method, headers };
  if (body) {
    options.body = JSON.stringify(body);
  }
  const resp = await fetch(url, options);
  let data: unknown;
  try {
    data = await resp.json();
  } catch {
    data = null;
  }
  return { status: resp.status, data };
}

/**
 * Backend API にログインして JWT トークンを取得する
 */
async function backendLogin(username: string, password: string): Promise<string> {
  const resp = await fetch(`${BACKEND_URL}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  const data = await resp.json() as { access_token: string };
  return data.access_token;
}

/**
 * Backend API のタスク一覧を取得する。
 * gitlab_project_id と source_iid はバックエンドAPIが未対応のため、
 * 全件取得後にクライアント側でフィルタリングする。
 */
async function getBackendTasks(token: string, params: Record<string, string> = {}): Promise<unknown[]> {
  // API 非対応のパラメータをクライアントフィルタ用に分離
  const { gitlab_project_id, source_iid, ...apiParams } = params;
  const query = new URLSearchParams(apiParams).toString();
  const resp = await fetch(`${BACKEND_URL}/api/tasks${query ? '?' + query : ''}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const data = await resp.json() as { items: unknown[] };
  let items: unknown[] = data.items ?? [];

  // gitlab_project_id と source_iid はクライアント側でフィルタ
  if (gitlab_project_id !== undefined) {
    items = items.filter(
      (t: unknown) => String((t as { gitlab_project_id: number }).gitlab_project_id) === gitlab_project_id
    );
  }
  if (source_iid !== undefined) {
    items = items.filter(
      (t: unknown) => String((t as { source_iid: number }).source_iid) === source_iid
    );
  }

  return items;
}

/**
 * GitLab の Issue を作成する
 */
async function createIssue(
  projectId: string,
  token: string,
  title: string,
  description = ''
): Promise<{ id: number; iid: number }> {
  const resp = await gitlabApi('POST', `/projects/${projectId}/issues`, token, {
    title,
    description,
  });
  expect(resp.status).toBe(201);
  return resp.data as { id: number; iid: number };
}

/**
 * GitLab の Issue にラベルとアサインを付与する（タスクトリガー操作）
 */
async function triggerIssue(
  projectId: string,
  issueIid: number,
  token: string,
  assigneeUsername: string,
  label: string
): Promise<void> {
  // アサイニーのユーザー ID を取得
  const userResp = await gitlabApi('GET', `/users?username=${assigneeUsername}`, token);
  const users = userResp.data as Array<{ id: number }>;
  expect(users.length).toBeGreaterThan(0);
  const assigneeId = users[0].id;

  // ラベル付与 + アサイン
  const resp = await gitlabApi('PUT', `/projects/${projectId}/issues/${issueIid}`, token, {
    assignee_ids: [assigneeId],
    labels: label,
  });
  expect(resp.status).toBe(200);
}

/**
 * GitLab の MR にラベルとアサインを付与する（F-4 タスクトリガー操作）
 */
async function triggerMR(
  projectId: string,
  mrIid: number,
  token: string,
  assigneeUsername: string,
  label: string
): Promise<void> {
  // アサイニーのユーザー ID を取得
  const userResp = await gitlabApi('GET', `/users?username=${assigneeUsername}`, token);
  const users = userResp.data as Array<{ id: number }>;
  expect(users.length).toBeGreaterThan(0);
  const assigneeId = users[0].id;

  // ラベル付与 + アサイン
  const resp = await gitlabApi('PUT', `/projects/${projectId}/merge_requests/${mrIid}`, token, {
    assignee_ids: [assigneeId],
    labels: label,
  });
  expect(resp.status).toBe(200);
}

/**
 * 指定条件が true になるまで待機するポーリングヘルパー
 */
async function waitUntil(
  condition: () => Promise<boolean>,
  timeoutMs = TASK_TIMEOUT_MS,
  intervalMs = POLLING_INTERVAL_MS
): Promise<boolean> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (await condition()) return true;
    await new Promise(resolve => setTimeout(resolve, intervalMs));
  }
  return false;
}

/**
 * GitLab の Issue/MR に特定テキストを含むコメントが投稿されるまで待機する
 */
async function waitForComment(
  projectId: string,
  resourceType: 'issues' | 'merge_requests',
  iid: number,
  token: string,
  expectedText: string,
  timeoutMs = TASK_TIMEOUT_MS
): Promise<boolean> {
  return waitUntil(async () => {
    const resp = await gitlabApi('GET', `/projects/${projectId}/${resourceType}/${iid}/notes`, token);
    if (resp.status !== 200) return false;
    const notes = resp.data as Array<{ body: string }>;
    return notes.some(note => note.body.includes(expectedText));
  }, timeoutMs);
}

/**
 * GitLab プロジェクトに Draft MR が作成されるまで待機する
 *
 * @param createdAfter このタイムスタンプ（ms）以降に作成された MR のみを対象とする。
 *   stale MR の誤検知防止のため、テスト開始時刻を渡すこと。
 */
async function waitForMR(
  projectId: string,
  token: string,
  branchPattern: RegExp,
  timeoutMs = TASK_TIMEOUT_MS,
  createdAfter?: number
): Promise<{ iid: number; title: string; source_branch: string } | null> {
  let foundMR: { iid: number; title: string; source_branch: string } | null = null;
  await waitUntil(async () => {
    const resp = await gitlabApi('GET', `/projects/${projectId}/merge_requests?state=opened`, token);
    if (resp.status !== 200) return false;
    const mrs = resp.data as Array<{ iid: number; title: string; source_branch: string; created_at: string }>;
    // createdAfter が指定されている場合はそれ以降に作成された MR のみを対象にする
    const filtered = createdAfter
      ? mrs.filter(mr => new Date(mr.created_at).getTime() >= createdAfter)
      : mrs;
    const mr = filtered.find(mr => branchPattern.test(mr.source_branch) || mr.title.startsWith('Draft:'));
    if (mr) { foundMR = mr; return true; }
    return false;
  }, timeoutMs);
  return foundMR;
}

/**
 * Backend のタスクが特定ステータスになるまで待機する
 */
async function waitForTaskStatus(
  token: string,
  projectId: string,
  issueIid: string,
  expectedStatus: string,
  timeoutMs = TASK_TIMEOUT_MS
): Promise<boolean> {
  return waitUntil(async () => {
    const tasks = await getBackendTasks(token, {
      gitlab_project_id: projectId,
      source_iid: issueIid,
    });
    return tasks.some((t: unknown) => (t as { status: string }).status === expectedStatus);
  }, timeoutMs);
}

/**
 * pending/running 状態のタスクがなくなるまで待機するヘルパー（キュー掃け待ち）
 *
 * 前のテストが起動した CLI タスク（F-3/F-4）がコンシューマーのキューに
 * バックログとして残っている場合、後続テストのタスクが TASK_TIMEOUT_MS 以内に
 * 処理されずに失敗することがある。
 * このヘルパーを使って全 pending/running タスクが完了してからテストを開始することで
 * キューバックログ起因の失敗を防ぐ。
 *
 * @param token Backend の JWT トークン
 * @param timeoutMs 待機タイムアウト（デフォルト: TASK_TIMEOUT_MS）
 */
async function waitForQueueDrain(
  token: string,
  timeoutMs = TASK_TIMEOUT_MS
): Promise<void> {
  await waitUntil(async () => {
    // プロジェクト/IID フィルタなしで全タスクを取得
    const tasks = await getBackendTasks(token);
    return !tasks.some(
      (t: unknown) => ['pending', 'running'].includes((t as { status: string }).status)
    );
  }, timeoutMs);
}

// -----------------------------------------------------------------------
// テスト前提条件チェック
// -----------------------------------------------------------------------

/**
 * GitLab と Backend の接続確認
 */
test.beforeAll(async () => {
  // 必須環境変数が未設定の場合はエラーで失敗させる（スキップしない）
  if (!GITLAB_ADMIN_TOKEN || !GITLAB_PROJECT_ID) {
    throw new Error(
      'GITLAB_ADMIN_TOKEN または GITLAB_PROJECT_ID が未設定です。\n' +
      'テスト実行前に scripts/test_setup.sh を実行してください。'
    );
  }
  if (!GITLAB_USER_TOKEN) {
    throw new Error(
      'GITLAB_USER_TOKEN が未設定です（testuser-claude の GitLab PAT）。\n' +
      'テスト実行前に scripts/test_setup.sh を実行してください。'
    );
  }
  if (!GITLAB_USER_TOKEN_OPENCODE) {
    throw new Error(
      'GITLAB_USER_TOKEN_OPENCODE が未設定です（testuser-opencode の GitLab PAT）。\n' +
      'テスト実行前に scripts/test_setup.sh を実行してください。'
    );
  }
});

// -----------------------------------------------------------------------
// T-04: Issue を Webhook で検出して MR 変換
// -----------------------------------------------------------------------

test('T-04: IssueをWebhookで検出してMR変換できる', async () => {
  const projectId = GITLAB_PROJECT_ID;
  const adminToken = BACKEND_URL ? await backendLogin('admin', ADMIN_PASSWORD) : '';
  const issueSuffix = Date.now();
  const issueTitle = `[E2E T-04] Webhook テスト Issue ${issueSuffix}`;

  // Issue 作成（testuser-claude として作成することで backend の users テーブルに存在するユーザーが author になる）
  const issue = await createIssue(projectId, GITLAB_USER_TOKEN, issueTitle,
    'E2E テスト: Webhook 経由で MR 変換を確認する');

  // bot アサイン + ラベル付与（Webhook でトリガー）—admin 権限で実施
  await triggerIssue(projectId, issue.iid, GITLAB_ADMIN_TOKEN, GITLAB_BOT_NAME, GITLAB_BOT_LABEL);

  // MR が作成されるまで待つ（最大120秒）
  const mr = await waitForMR(projectId, GITLAB_ADMIN_TOKEN, /.*/, TASK_TIMEOUT_MS);
  expect(mr).not.toBeNull();

  // Issue にコメントが投稿されていることを確認
  const commented = await waitForComment(
    projectId, 'issues', issue.iid, GITLAB_ADMIN_TOKEN, 'MR', TASK_TIMEOUT_MS
  );
  expect(commented).toBe(true);
});

// -----------------------------------------------------------------------
// T-05: Issue をポーリングで MR 変換
// -----------------------------------------------------------------------

test('T-05: IssueをポーリングでMR変換できる', async () => {
  const projectId = GITLAB_PROJECT_ID;
  const issueSuffix = Date.now();
  const issueTitle = `[E2E T-05] ポーリング テスト Issue ${issueSuffix}`;

  // Issue 作成（testuser-claude として作成することで backend の users テーブルに存在するユーザーが author になる）
  const issue = await createIssue(projectId, GITLAB_USER_TOKEN, issueTitle,
    'E2E テスト: ポーリング経由で MR 変換を確認する');
  // bot アサイン + ラベル付与—admin 権限で実施
  await triggerIssue(projectId, issue.iid, GITLAB_ADMIN_TOKEN, GITLAB_BOT_NAME, GITLAB_BOT_LABEL);

  // ポーリング間隔（10秒設定）+ 処理時間を考慮して MR 作成を待つ
  const mr = await waitForMR(projectId, GITLAB_ADMIN_TOKEN, /.*/, TASK_TIMEOUT_MS);
  expect(mr).not.toBeNull();
  expect(mr!.title).toMatch(/Draft:/);
});

// -----------------------------------------------------------------------
// T-06: MR 変換後に bot アサイン・ラベルが引き継がれる
// -----------------------------------------------------------------------

test('T-06: MR変換後にbotアサイン・ラベルが引き継がれる', async () => {
  const projectId = GITLAB_PROJECT_ID;
  const issueSuffix = Date.now();
  const issueTitle = `[E2E T-06] アサイン引き継ぎテスト ${issueSuffix}`;

  // Issue 作成（testuser-claude として作成することで backend の users テーブルに存在するユーザーが author になる）
  const issue = await createIssue(projectId, GITLAB_USER_TOKEN, issueTitle, 'T-06 test');
  // bot アサイン + ラベル付与—admin 権限で実施
  await triggerIssue(projectId, issue.iid, GITLAB_ADMIN_TOKEN, GITLAB_BOT_NAME, GITLAB_BOT_LABEL);

  // MR が作成されるのを待つ
  const mr = await waitForMR(projectId, GITLAB_ADMIN_TOKEN, /.*/, TASK_TIMEOUT_MS);
  expect(mr).not.toBeNull();

  // MR の詳細を確認
  const mrDetail = await gitlabApi(
    'GET',
    `/projects/${projectId}/merge_requests/${mr!.iid}`,
    GITLAB_ADMIN_TOKEN
  );
  const mrData = mrDetail.data as {
    assignees: Array<{ username: string }>;
    labels: string[];
  };

  // bot がアサインされている
  const hasBotAssignee = mrData.assignees.some(a => a.username === GITLAB_BOT_NAME);
  expect(hasBotAssignee).toBe(true);

  // ラベルが含まれている
  const hasLabel = mrData.labels.some(l => l.includes('coding agent'));
  expect(hasLabel).toBe(true);
});

// -----------------------------------------------------------------------
// T-10: 未登録ユーザーの Issue は処理されない
// -----------------------------------------------------------------------

test('T-10: 未登録ユーザーのIssueは処理されない', async () => {
  const projectId = GITLAB_PROJECT_ID;
  const issueSuffix = Date.now();
  const issueTitle = `[E2E T-10] 未登録ユーザーテスト ${issueSuffix}`;

  // 未登録ユーザー（GitLab には存在するが本システムには未登録）の Issue を作成
  // 管理者アカウントで作成するが、adminをシステムから削除してテストするのは複雑なため
  // 存在しないユーザー名でアサインを試みる
  const issue = await createIssue(projectId, GITLAB_ADMIN_TOKEN, issueTitle, 'T-10 test');

  // 存在しないユーザー名でアサインしようとする（エラーになるか無視される）
  const userResp = await gitlabApi('GET', `/users?username=nonexistent-user-${issueSuffix}`, GITLAB_ADMIN_TOKEN);
  const users = userResp.data as Array<{ id: number }>;

  if (users.length === 0) {
    // 未登録ユーザーは GitLab に存在しないのでアサインできない
    // ラベルのみ付与してシステムが反応しないことを確認
    await gitlabApi('PUT', `/projects/${projectId}/issues/${issue.iid}`, GITLAB_ADMIN_TOKEN, {
      labels: GITLAB_BOT_LABEL,
    });

    // タスクが作成されないことを確認（10秒待って確認）
    await new Promise(resolve => setTimeout(resolve, 10_000));
    const adminToken = await backendLogin('admin', ADMIN_PASSWORD);
    const tasks = await getBackendTasks(adminToken, {
      gitlab_project_id: projectId,
      source_iid: String(issue.iid),
    });
    // タスクが作成されていないか、または failed になっている
    const hasRunningTask = tasks.some(
      (t: unknown) => ['pending', 'running'].includes((t as { status: string }).status)
    );
    expect(hasRunningTask).toBe(false);
  }
});

// -----------------------------------------------------------------------
// T-11: bot アサインのみでは処理されない（ラベルなし）
// -----------------------------------------------------------------------

test('T-11: botアサインのみでは処理されない（ラベルなし）', async () => {
  const projectId = GITLAB_PROJECT_ID;
  const issueSuffix = Date.now();
  const issueTitle = `[E2E T-11] アサインのみテスト ${issueSuffix}`;

  const issue = await createIssue(projectId, GITLAB_ADMIN_TOKEN, issueTitle, 'T-11 test');

  // bot アサインのみ（ラベルなし）
  const userResp = await gitlabApi('GET', `/users?username=${GITLAB_BOT_NAME}`, GITLAB_ADMIN_TOKEN);
  const users = userResp.data as Array<{ id: number }>;
  if (users.length > 0) {
    await gitlabApi('PUT', `/projects/${projectId}/issues/${issue.iid}`, GITLAB_ADMIN_TOKEN, {
      assignee_ids: [users[0].id],
    });
  }

  // 15秒待ってタスクが作成されないことを確認
  await new Promise(resolve => setTimeout(resolve, 15_000));
  const adminToken = await backendLogin('admin', ADMIN_PASSWORD);
  const tasks = await getBackendTasks(adminToken, {
    gitlab_project_id: projectId,
    source_iid: String(issue.iid),
  });
  expect(tasks.length).toBe(0);
});

// -----------------------------------------------------------------------
// T-12: ラベルのみでは処理されない（bot アサインなし）
// -----------------------------------------------------------------------

test('T-12: ラベルのみでは処理されない（botアサインなし）', async () => {
  const projectId = GITLAB_PROJECT_ID;
  const issueSuffix = Date.now();
  const issueTitle = `[E2E T-12] ラベルのみテスト ${issueSuffix}`;

  const issue = await createIssue(projectId, GITLAB_ADMIN_TOKEN, issueTitle, 'T-12 test');

  // ラベルのみ付与（bot アサインなし）
  await gitlabApi('PUT', `/projects/${projectId}/issues/${issue.iid}`, GITLAB_ADMIN_TOKEN, {
    labels: GITLAB_BOT_LABEL,
  });

  // 15秒待ってタスクが作成されないことを確認
  await new Promise(resolve => setTimeout(resolve, 15_000));
  const adminToken = await backendLogin('admin', ADMIN_PASSWORD);
  const tasks = await getBackendTasks(adminToken, {
    gitlab_project_id: projectId,
    source_iid: String(issue.iid),
  });
  expect(tasks.length).toBe(0);
});

// -----------------------------------------------------------------------
// T-13: 無効化ユーザーの Issue は処理されない
// -----------------------------------------------------------------------

test('T-13: 無効化ユーザーのIssueは処理されない', async () => {
  const projectId = GITLAB_PROJECT_ID;
  const issueSuffix = Date.now();
  const adminToken = await backendLogin('admin', ADMIN_PASSWORD);

  // テスト用ユーザーを作成して無効化する
  const disabledUsername = `disabled-user-${issueSuffix}`;
  const disabledEmail = `disabled-${issueSuffix}@example.com`;

  // Backend にユーザー登録
  const createResp = await fetch(`${BACKEND_URL}/api/users`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${adminToken}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      username: disabledUsername,
      email: disabledEmail,
      password: 'Test@123456',
      virtual_key: 'sk-mock-disabled-key',
      default_cli: 'claude',
      default_model: process.env.DEFAULT_CLAUDE_MODEL || 'claude-haiku-4-5-20251001',
      role: 'user',
    }),
  });
  // ユーザー作成成功または既存を確認
  expect([200, 201, 409]).toContain(createResp.status);

  // ユーザーを無効化（is_active = false）
  const disableResp = await fetch(`${BACKEND_URL}/api/users/${disabledUsername}`, {
    method: 'PUT',
    headers: { Authorization: `Bearer ${adminToken}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ is_active: false }),
  });
  expect(disableResp.status).toBe(200);

  // GitLab にも同ユーザーを作成してアサインに使用する
  const glUserResp = await gitlabApi('POST', '/users', GITLAB_ADMIN_TOKEN, {
    username: disabledUsername,
    email: disabledEmail,
    password: 'Test@SecurePassword123!',
    name: `Disabled User ${issueSuffix}`,
    skip_confirmation: true,
  });
  let disabledGlUserId: number;
  if (glUserResp.status === 201) {
    disabledGlUserId = (glUserResp.data as { id: number }).id;
    // プロジェクトメンバーに追加
    await gitlabApi('POST', `/projects/${projectId}/members`, GITLAB_ADMIN_TOKEN, {
      user_id: disabledGlUserId,
      access_level: 40,
    });
  } else if (glUserResp.status === 409) {
    const existing = await gitlabApi('GET', `/users?username=${disabledUsername}`, GITLAB_ADMIN_TOKEN);
    disabledGlUserId = (existing.data as Array<{ id: number }>)[0].id;
  } else {
    // GitLab ユーザー作成に失敗した場合はスキップ
    console.warn('GitLab テストユーザー作成失敗、T-13 をスキップします');
    return;
  }

  // Issue 作成
  const issue = await createIssue(projectId, GITLAB_ADMIN_TOKEN,
    `[E2E T-13] 無効化ユーザーテスト ${issueSuffix}`, 'T-13 test');

  // 無効化ユーザーのアサイン + ラベル付与
  await gitlabApi('PUT', `/projects/${projectId}/issues/${issue.iid}`, GITLAB_ADMIN_TOKEN, {
    assignee_ids: [disabledGlUserId],
    labels: GITLAB_BOT_LABEL,
  });

  // 15秒待ってタスクが pending/running にならないことを確認
  await new Promise(resolve => setTimeout(resolve, 15_000));

  const tasks = await getBackendTasks(adminToken, {
    gitlab_project_id: projectId,
    source_iid: String(issue.iid),
  });
  const hasActiveTask = tasks.some(
    (t: unknown) => ['pending', 'running'].includes((t as { status: string }).status)
  );
  expect(hasActiveTask).toBe(false);
});

// -----------------------------------------------------------------------
// T-24: Webhook とポーリングが同時検出しても重複処理されない
// -----------------------------------------------------------------------

test('T-24: WebhookとポーリングがIssueを同時検出しても重複処理されない', async () => {
  const projectId = GITLAB_PROJECT_ID;
  const issueSuffix = Date.now();
  const issueTitle = `[E2E T-24] 重複チェックテスト ${issueSuffix}`;

  // Issue 作成（testuser-claude として作成することで backend の users テーブルに存在するユーザーが author になる）
  const issue = await createIssue(projectId, GITLAB_USER_TOKEN, issueTitle, 'T-24 test');
  // bot アサイン + ラベル付与—admin 権限で実施
  await triggerIssue(projectId, issue.iid, GITLAB_ADMIN_TOKEN, GITLAB_BOT_NAME, GITLAB_BOT_LABEL);

  // タスクが処理されるまで待つ
  const adminToken = await backendLogin('admin', ADMIN_PASSWORD);
  await waitForTaskStatus(adminToken, projectId, String(issue.iid), 'completed', TASK_TIMEOUT_MS);

  // タスクが1件のみ作成されていることを確認
  const tasks = await getBackendTasks(adminToken, {
    gitlab_project_id: projectId,
    source_iid: String(issue.iid),
  });
  expect(tasks.length).toBe(1);
});

// -----------------------------------------------------------------------
// T-28: MR 処理中に CLI 出力が1つの進捗コメントに定期更新される
// -----------------------------------------------------------------------

test('T-28: MR処理中にCLI出力が進捗コメントに定期更新される', async () => {
  const projectId = GITLAB_PROJECT_ID;
  const issueSuffix = Date.now();
  // このテスト開始時刻以降に作成された MR のみを対象にする（stale MR 誤検知防止）
  const testStartTime = Date.now();

  // まず Issue を作成して MR に変換する（testuser-claude として作成）
  const issue = await createIssue(
    projectId, GITLAB_USER_TOKEN,
    `[E2E T-28] 進捗コメントテスト ${issueSuffix}`,
    '処理時間が長い作業のため、進捗コメントが定期更新されることを確認する'
  );
  // bot アサイン + ラベル付与—admin 権限で実施
  await triggerIssue(projectId, issue.iid, GITLAB_ADMIN_TOKEN, GITLAB_BOT_NAME, GITLAB_BOT_LABEL);

  // MR が作成されるまで待つ（テスト開始後に作成された MR のみを対象にする）
  const mr = await waitForMR(projectId, GITLAB_ADMIN_TOKEN, /.*/, TASK_TIMEOUT_MS, testStartTime);
  expect(mr).not.toBeNull();

  // MR にトリガーを付与（F-4 処理開始）
  await triggerMR(projectId, mr!.iid, GITLAB_ADMIN_TOKEN, GITLAB_BOT_NAME, GITLAB_BOT_LABEL);

  // 進捗コメントが投稿されるまで待つ（<details> 形式のコメント）
  const hasProgressComment = await waitForComment(
    projectId, 'merge_requests', mr!.iid, GITLAB_ADMIN_TOKEN,
    '<details>', // <details> タグが含まれる進捗コメントを確認
    TASK_TIMEOUT_MS
  );
  expect(hasProgressComment).toBe(true);

  // 処理完了後のコメントも確認（"completed" または "done" を含む）
  const hasCompletionComment = await waitForComment(
    projectId, 'merge_requests', mr!.iid, GITLAB_ADMIN_TOKEN,
    '完了',
    TASK_TIMEOUT_MS
  );
  expect(hasCompletionComment).toBe(true);
});

// -----------------------------------------------------------------------
// T-30: MR 処理中に bot のアサインが解除されたら CLI が強制終了する
// -----------------------------------------------------------------------

test('T-30: MR処理中にbotのアサインが解除されたらCLIが強制終了される', async () => {
  const projectId = GITLAB_PROJECT_ID;
  const issueSuffix = Date.now();
  const adminToken = await backendLogin('admin', ADMIN_PASSWORD);
  // このテスト開始時刻以降に作成された MR のみを対象にする（stale MR 誤検知防止）
  const testStartTime = Date.now();

  // まず Issue を作成して MR に変換する（testuser-claude として作成）
  const issue = await createIssue(
    projectId, GITLAB_USER_TOKEN,
    `[E2E T-30] アサイン解除テスト ${issueSuffix}`,
    '処理中に bot のアサインを解除して強制終了を確認する'
  );
  // bot アサイン + ラベル付与—admin 権限で実施
  await triggerIssue(projectId, issue.iid, GITLAB_ADMIN_TOKEN, GITLAB_BOT_NAME, GITLAB_BOT_LABEL);

  // MR が作成されるまで待つ（テスト開始後に作成された MR のみを対象にする）
  const mr = await waitForMR(projectId, GITLAB_ADMIN_TOKEN, /.*/, TASK_TIMEOUT_MS, testStartTime);
  expect(mr).not.toBeNull();

  // MR に bot をアサイン + ラベル付与（F-4 処理開始）
  await triggerMR(projectId, mr!.iid, GITLAB_ADMIN_TOKEN, GITLAB_BOT_NAME, GITLAB_BOT_LABEL);

  // Consumer が処理を開始するまで少し待つ（進捗コメントが出たら処理開始の合図）
  await waitForComment(
    projectId, 'merge_requests', mr!.iid, GITLAB_ADMIN_TOKEN,
    '<details>', 30_000  // 最大30秒待つ
  );

  // bot のアサインを解除する
  await gitlabApi('PUT', `/projects/${projectId}/merge_requests/${mr!.iid}`, GITLAB_ADMIN_TOKEN, {
    assignee_ids: [],
  });

  // タスクが failed になるまで待つ（レースコンディション耐性のため2倍のタイムアウトを設定）
  const taskFailed = await waitUntil(async () => {
    const tasks = await getBackendTasks(adminToken, {
      gitlab_project_id: projectId,
      source_iid: String(mr!.iid),
    });
    return tasks.some((t: unknown) => (t as { status: string }).status === 'failed');
  }, TASK_TIMEOUT_MS * 2);
  expect(taskFailed).toBe(true);

  // MR に強制終了コメントが投稿されていることを確認
  const hasForceStopComment = await waitForComment(
    projectId, 'merge_requests', mr!.iid, GITLAB_ADMIN_TOKEN,
    '強制終了',
    30_000
  );
  expect(hasForceStopComment).toBe(true);
});

// -----------------------------------------------------------------------
// T-31: testuser-opencode の Issue を opencode CLI で MR 変換できる
// -----------------------------------------------------------------------

test('T-31: testuser-opencodeのIssueをopencode CLIでMR変換できる', async () => {
  const projectId = GITLAB_PROJECT_ID;
  const issueSuffix = Date.now();
  const issueTitle = `[E2E T-31] opencode MR変換テスト ${issueSuffix}`;

  const adminToken = await backendLogin('admin', ADMIN_PASSWORD);

  // 前のテスト（T-28/T-30）の CLI タスク（F-4）がコンシューマーキューに残っている場合、
  // T-31 の F-3 タスクが TASK_TIMEOUT_MS 以内に処理されず失敗する。
  // キューが空になってから Issue を投入することで競合を防ぐ。
  await waitForQueueDrain(adminToken, TASK_TIMEOUT_MS);

  // testuser-opencode として Issue を作成（バックエンドの users テーブルに opencode ユーザーとして登録済み）
  const issue = await createIssue(
    projectId, GITLAB_USER_TOKEN_OPENCODE, issueTitle,
    'E2E テスト: opencode CLI で Issue を MR 変換することを確認する'
  );

  // bot アサイン + ラベル付与（admin 権限で実施）
  await triggerIssue(projectId, issue.iid, GITLAB_ADMIN_TOKEN, GITLAB_BOT_NAME, GITLAB_BOT_LABEL);

  // Backend タスクが completed になるまで待つ（既存 MR の誤検知を避けるため waitForMR の代わりに使用）
  const completed = await waitForTaskStatus(
    adminToken, projectId, String(issue.iid), 'completed', TASK_TIMEOUT_MS
  );
  expect(completed).toBe(true);

  // Issue に MR リンクのコメントが投稿されていることを確認
  const commented = await waitForComment(
    projectId, 'issues', issue.iid, GITLAB_ADMIN_TOKEN, 'MR', TASK_TIMEOUT_MS
  );
  expect(commented).toBe(true);
});

// -----------------------------------------------------------------------
// T-32: testuser-opencode の MR を opencode CLI で処理できる
// -----------------------------------------------------------------------

test('T-32: testuser-opencodeのMRをopencode CLIで処理できる', async () => {
  const projectId = GITLAB_PROJECT_ID;
  const issueSuffix = Date.now();

  // このテスト開始時刻以降に作成された MR のみを対象にする（stale MR 誤検知防止）
  const testStartTime = Date.now();

  // testuser-opencode として Issue を作成して MR に変換する
  const issue = await createIssue(
    projectId, GITLAB_USER_TOKEN_OPENCODE,
    `[E2E T-32] opencode MR処理テスト ${issueSuffix}`,
    'E2E テスト: opencode CLI で MR を処理することを確認する'
  );
  // bot アサイン + ラベル付与（admin 権限で実施）
  await triggerIssue(projectId, issue.iid, GITLAB_ADMIN_TOKEN, GITLAB_BOT_NAME, GITLAB_BOT_LABEL);

  // MR が作成されるまで待つ（テスト開始後に作成された MR のみを対象にする）
  const mr = await waitForMR(projectId, GITLAB_ADMIN_TOKEN, /.*/, TASK_TIMEOUT_MS, testStartTime);
  expect(mr).not.toBeNull();

  // MR に bot をアサイン + ラベル付与（F-4: MR CLI 処理開始）
  await triggerMR(projectId, mr!.iid, GITLAB_ADMIN_TOKEN, GITLAB_BOT_NAME, GITLAB_BOT_LABEL);

  // 進捗コメントが投稿されるまで待つ（<details> タグを含む進捗コメント）
  const hasProgressComment = await waitForComment(
    projectId, 'merge_requests', mr!.iid, GITLAB_ADMIN_TOKEN,
    '<details>',
    TASK_TIMEOUT_MS
  );
  expect(hasProgressComment).toBe(true);

  // 処理完了後の完了コメントを確認
  const hasCompletionComment = await waitForComment(
    projectId, 'merge_requests', mr!.iid, GITLAB_ADMIN_TOKEN,
    '完了',
    TASK_TIMEOUT_MS
  );
  expect(hasCompletionComment).toBe(true);
});
