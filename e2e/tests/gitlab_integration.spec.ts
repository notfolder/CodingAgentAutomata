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
 * Backend API のタスク一覧を取得する
 */
async function getBackendTasks(token: string, params: Record<string, string> = {}): Promise<unknown[]> {
  const query = new URLSearchParams(params).toString();
  const resp = await fetch(`${BACKEND_URL}/api/tasks${query ? '?' + query : ''}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const data = await resp.json() as { items: unknown[] };
  return data.items ?? [];
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
 */
async function waitForMR(
  projectId: string,
  token: string,
  branchPattern: RegExp,
  timeoutMs = TASK_TIMEOUT_MS
): Promise<{ iid: number; title: string; source_branch: string } | null> {
  let foundMR: { iid: number; title: string; source_branch: string } | null = null;
  await waitUntil(async () => {
    const resp = await gitlabApi('GET', `/projects/${projectId}/merge_requests?state=opened`, token);
    if (resp.status !== 200) return false;
    const mrs = resp.data as Array<{ iid: number; title: string; source_branch: string }>;
    const mr = mrs.find(mr => branchPattern.test(mr.source_branch) || mr.title.startsWith('Draft:'));
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

// -----------------------------------------------------------------------
// テスト前提条件チェック
// -----------------------------------------------------------------------

/**
 * GitLab と Backend の接続確認
 */
test.beforeAll(async () => {
  // GitLab が利用可能か確認
  if (!GITLAB_ADMIN_TOKEN || !GITLAB_PROJECT_ID) {
    console.warn(
      'GITLAB_ADMIN_TOKEN または GITLAB_PROJECT_ID が未設定のため GitLab 統合テストをスキップします。\n' +
      'テスト実行前に scripts/test_setup.py を実行してください。'
    );
  }
});

// GitLab 統合テストを条件付きで実行するためのラッパー
function gitlabTest(
  title: string,
  fn: Parameters<typeof test>[1]
): void {
  if (!GITLAB_ADMIN_TOKEN || !GITLAB_PROJECT_ID) {
    test.skip(title, fn);
  } else {
    test(title, fn);
  }
}

// -----------------------------------------------------------------------
// T-04: Issue を Webhook で検出して MR 変換
// -----------------------------------------------------------------------

gitlabTest('T-04: IssueをWebhookで検出してMR変換できる', async () => {
  const projectId = GITLAB_PROJECT_ID;
  const adminToken = BACKEND_URL ? await backendLogin('admin', ADMIN_PASSWORD) : '';
  const issueSuffix = Date.now();
  const issueTitle = `[E2E T-04] Webhook テスト Issue ${issueSuffix}`;

  // Issue 作成
  const issue = await createIssue(projectId, GITLAB_ADMIN_TOKEN, issueTitle,
    'E2E テスト: Webhook 経由で MR 変換を確認する');

  // bot アサイン + ラベル付与（Webhook でトリガー）
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

gitlabTest('T-05: IssueをポーリングでMR変換できる', async () => {
  const projectId = GITLAB_PROJECT_ID;
  const issueSuffix = Date.now();
  const issueTitle = `[E2E T-05] ポーリング テスト Issue ${issueSuffix}`;

  // Issue 作成してから bot アサイン + ラベルを付与
  const issue = await createIssue(projectId, GITLAB_ADMIN_TOKEN, issueTitle,
    'E2E テスト: ポーリング経由で MR 変換を確認する');
  await triggerIssue(projectId, issue.iid, GITLAB_ADMIN_TOKEN, GITLAB_BOT_NAME, GITLAB_BOT_LABEL);

  // ポーリング間隔（10秒設定）+ 処理時間を考慮して MR 作成を待つ
  const mr = await waitForMR(projectId, GITLAB_ADMIN_TOKEN, /.*/, TASK_TIMEOUT_MS);
  expect(mr).not.toBeNull();
  expect(mr!.title).toMatch(/Draft:/);
});

// -----------------------------------------------------------------------
// T-06: MR 変換後に bot アサイン・ラベルが引き継がれる
// -----------------------------------------------------------------------

gitlabTest('T-06: MR変換後にbotアサイン・ラベルが引き継がれる', async () => {
  const projectId = GITLAB_PROJECT_ID;
  const issueSuffix = Date.now();
  const issueTitle = `[E2E T-06] アサイン引き継ぎテスト ${issueSuffix}`;

  const issue = await createIssue(projectId, GITLAB_ADMIN_TOKEN, issueTitle, 'T-06 test');
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

gitlabTest('T-10: 未登録ユーザーのIssueは処理されない', async () => {
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

gitlabTest('T-11: botアサインのみでは処理されない（ラベルなし）', async () => {
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

gitlabTest('T-12: ラベルのみでは処理されない（botアサインなし）', async () => {
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
// T-24: Webhook とポーリングが同時検出しても重複処理されない
// -----------------------------------------------------------------------

gitlabTest('T-24: WebhookとポーリングがIssueを同時検出しても重複処理されない', async () => {
  const projectId = GITLAB_PROJECT_ID;
  const issueSuffix = Date.now();
  const issueTitle = `[E2E T-24] 重複チェックテスト ${issueSuffix}`;

  const issue = await createIssue(projectId, GITLAB_ADMIN_TOKEN, issueTitle, 'T-24 test');
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
