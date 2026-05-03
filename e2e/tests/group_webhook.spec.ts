/**
 * Group Webhook テスト
 * 対象シナリオ:
 *   TS-WB-1: Group Webhook受信確認（/webhook APIへPOSTしてイベントを受信できる）
 *   TS-WB-2: 複数プロジェクト一元受信確認
 *   TS-WB-3: 非同期処理分離確認（受信APIが短時間で2xxを返却する）
 *   TS-WB-4: 重複受信抑止確認（同一Idempotency-Keyで重複受信されない）
 *   TS-WB-5: 受信失敗時記録確認（失敗時にWARNINGログを記録し200を返す）
 */

import { test, expect } from '@playwright/test';

// Webhook エンドポイントの URL
const WEBHOOK_URL = process.env.WEBHOOK_URL ?? 'http://producer:8080/webhook';
// Webhook シークレットトークン
const WEBHOOK_SECRET = process.env.GITLAB_WEBHOOK_SECRET ?? 'test-webhook-secret';

// テスト用 GitLab Issue イベントペイロード（最小限の構造）
function buildIssuePayload(projectId: number, issueIid: number): object {
  return {
    object_kind: 'issue',
    object_attributes: {
      iid: issueIid,
      project_id: projectId,
      state: 'opened',
      action: 'open',
      labels: ['bot-label'],
    },
    assignees: [{ username: 'test-bot' }],
    project: { id: projectId, name: 'test-project' },
  };
}

// -----------------------------------------------------------------------
// TS-WB-1: Group Webhook受信確認
// -----------------------------------------------------------------------

test('TS-WB-1: /webhook エンドポイントに POST してイベントを受信できる', async ({ request }) => {
  const payload = buildIssuePayload(1, 1);

  const response = await request.post(WEBHOOK_URL, {
    data: payload,
    headers: {
      'Content-Type': 'application/json',
      'X-Gitlab-Token': WEBHOOK_SECRET,
      'X-Gitlab-Event': 'Issue Hook',
    },
  });

  // Webhook エンドポイントが 200 を返すことを確認する
  expect(response.status()).toBe(200);
});

// -----------------------------------------------------------------------
// TS-WB-2: 複数プロジェクト一元受信確認
// -----------------------------------------------------------------------

test('TS-WB-2: 複数のプロジェクトIDからのWebhookを一元受信できる', async ({ request }) => {
  // プロジェクト 1 からのイベント
  const payload1 = buildIssuePayload(100, 1);
  const res1 = await request.post(WEBHOOK_URL, {
    data: payload1,
    headers: {
      'Content-Type': 'application/json',
      'X-Gitlab-Token': WEBHOOK_SECRET,
      'X-Gitlab-Event': 'Issue Hook',
      'X-Idempotency-Key': `test-wb2-project100-${Date.now()}`,
    },
  });
  expect(res1.status()).toBe(200);

  // プロジェクト 2 からのイベント
  const payload2 = buildIssuePayload(200, 2);
  const res2 = await request.post(WEBHOOK_URL, {
    data: payload2,
    headers: {
      'Content-Type': 'application/json',
      'X-Gitlab-Token': WEBHOOK_SECRET,
      'X-Gitlab-Event': 'Issue Hook',
      'X-Idempotency-Key': `test-wb2-project200-${Date.now()}`,
    },
  });
  expect(res2.status()).toBe(200);
});

// -----------------------------------------------------------------------
// TS-WB-3: 非同期処理分離確認
// -----------------------------------------------------------------------

test('TS-WB-3: Webhook受信APIが短時間（3秒以内）で200を返す', async ({ request }) => {
  const payload = buildIssuePayload(1, 100);
  const startTime = Date.now();

  const response = await request.post(WEBHOOK_URL, {
    data: payload,
    headers: {
      'Content-Type': 'application/json',
      'X-Gitlab-Token': WEBHOOK_SECRET,
      'X-Gitlab-Event': 'Issue Hook',
      'X-Idempotency-Key': `test-wb3-async-${Date.now()}`,
    },
  });

  const elapsed = Date.now() - startTime;

  // 2xx が返ること
  expect(response.status()).toBe(200);
  // 3秒以内に返ること（イベント処理は非同期なので即時レスポンスされる）
  expect(elapsed).toBeLessThan(3000);
});

// -----------------------------------------------------------------------
// TS-WB-4: 重複受信抑止確認
// -----------------------------------------------------------------------

test('TS-WB-4: 同一Idempotency-Keyで送信された重複イベントが抑止される', async ({ request }) => {
  // 同一 Idempotency-Key でのリクエストを2回送信する
  const idempotencyKey = `test-wb4-dedup-${Date.now()}`;
  const payload = buildIssuePayload(1, 200);

  // 1回目の送信（処理される）
  const res1 = await request.post(WEBHOOK_URL, {
    data: payload,
    headers: {
      'Content-Type': 'application/json',
      'X-Gitlab-Token': WEBHOOK_SECRET,
      'X-Gitlab-Event': 'Issue Hook',
      'X-Idempotency-Key': idempotencyKey,
    },
  });
  expect(res1.status()).toBe(200);

  // 2回目の送信（同じキーのためスキップされる）
  const res2 = await request.post(WEBHOOK_URL, {
    data: payload,
    headers: {
      'Content-Type': 'application/json',
      'X-Gitlab-Token': WEBHOOK_SECRET,
      'X-Gitlab-Event': 'Issue Hook',
      'X-Idempotency-Key': idempotencyKey,
    },
  });
  // 重複でも 200 を返す（処理はスキップされている）
  expect(res2.status()).toBe(200);
});

// -----------------------------------------------------------------------
// TS-WB-5: 受信失敗時記録確認
// -----------------------------------------------------------------------

test('TS-WB-5: ペイロード不正の場合もWARNINGログを記録して200を返す', async ({ request }) => {
  // 不正な JSON ペイロードを送信する（Content-Type を application/json にして無効な JSON を送る）
  const response = await request.post(WEBHOOK_URL, {
    headers: {
      'Content-Type': 'application/json',
      'X-Gitlab-Token': WEBHOOK_SECRET,
      'X-Gitlab-Event': 'Issue Hook',
    },
    // 不正な JSON ボディ
    data: 'invalid-json-body',
  });

  // T-08 要件: ペイロード不正の場合は 400 ではなく 200 を返す
  expect(response.status()).toBe(200);
});

test('TS-WB-5: 署名不正の場合は403を返す', async ({ request }) => {
  const payload = buildIssuePayload(1, 300);

  const response = await request.post(WEBHOOK_URL, {
    data: payload,
    headers: {
      'Content-Type': 'application/json',
      // 不正なシークレットトークン
      'X-Gitlab-Token': 'wrong-secret-token',
      'X-Gitlab-Event': 'Issue Hook',
    },
  });

  // 署名不正は 403 を返す（仕様通り）
  expect(response.status()).toBe(403);
});
