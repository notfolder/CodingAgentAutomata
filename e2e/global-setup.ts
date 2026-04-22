/**
 * Playwright グローバルセットアップ
 *
 * 全テスト実行前に GitLab のオープン MR をすべてクローズし、
 * RabbitMQ の tasks キューをパージして、
 * テスト間のデータ混入（waitForMR が過去のMRを掴む問題）を防ぐ。
 */

import { request } from '@playwright/test';

async function purgeRabbitMQQueue(): Promise<void> {
  const RABBITMQ_USER = process.env.RABBITMQ_DEFAULT_USER ?? 'guest';
  const RABBITMQ_PASS = process.env.RABBITMQ_DEFAULT_PASS ?? 'guest';
  const RABBITMQ_MGMT_URL = process.env.RABBITMQ_MGMT_URL ?? 'http://rabbitmq:15672';
  const QUEUE_NAME = 'tasks';

  const mgmtContext = await request.newContext({ baseURL: RABBITMQ_MGMT_URL });
  try {
    const auth = Buffer.from(`${RABBITMQ_USER}:${RABBITMQ_PASS}`).toString('base64');
    const resp = await mgmtContext.delete(
      `/api/queues/%2F/${QUEUE_NAME}/contents`,
      { headers: { 'Authorization': `Basic ${auth}` } }
    );
    if (resp.status() === 204 || resp.status() === 200) {
      console.log(`[globalSetup] RabbitMQ キュー "${QUEUE_NAME}" をパージしました`);
    } else {
      console.log(`[globalSetup] RabbitMQ キューパージ: status=${resp.status()} (無視)`);
    }
  } catch (e) {
    console.log('[globalSetup] RabbitMQ キューパージに失敗しました（無視）:', e);
  } finally {
    await mgmtContext.dispose();
  }
}

async function globalSetup(): Promise<void> {
  const GITLAB_API_URL = process.env.GITLAB_API_URL ?? 'http://gitlab:8929';
  const GITLAB_ADMIN_TOKEN = process.env.GITLAB_ADMIN_TOKEN ?? '';
  const GITLAB_PROJECT_ID = process.env.GITLAB_PROJECT_ID ?? '';

  if (!GITLAB_ADMIN_TOKEN || !GITLAB_PROJECT_ID) {
    console.log('[globalSetup] GITLAB_ADMIN_TOKEN または GITLAB_PROJECT_ID が未設定のためスキップします');
    return;
  }

  // RabbitMQ キューをパージして古いタスクをクリア
  await purgeRabbitMQQueue();

  const apiContext = await request.newContext({ baseURL: GITLAB_API_URL });

  try {
    // オープン MR を取得（最大100件）
    const response = await apiContext.get(
      `/api/v4/projects/${GITLAB_PROJECT_ID}/merge_requests?state=opened&per_page=100`,
      { headers: { 'PRIVATE-TOKEN': GITLAB_ADMIN_TOKEN } }
    );

    if (!response.ok()) {
      console.log(`[globalSetup] MR 一覧取得失敗: ${response.status()}`);
      return;
    }

    const mrs = await response.json() as Array<{ iid: number; title: string }>;
    if (mrs.length === 0) {
      console.log('[globalSetup] クローズ対象のオープン MR はありません');
      return;
    }

    console.log(`[globalSetup] オープン MR を ${mrs.length} 件クローズします...`);
    for (const mr of mrs) {
      const closeResp = await apiContext.put(
        `/api/v4/projects/${GITLAB_PROJECT_ID}/merge_requests/${mr.iid}`,
        {
          headers: {
            'PRIVATE-TOKEN': GITLAB_ADMIN_TOKEN,
            'Content-Type': 'application/json',
          },
          data: { state_event: 'close' },
        }
      );
      if (closeResp.ok()) {
        console.log(`[globalSetup]   MR #${mr.iid} "${mr.title}" をクローズしました`);
      } else {
        console.log(`[globalSetup]   MR #${mr.iid} クローズ失敗: ${closeResp.status()}`);
      }
    }
    console.log('[globalSetup] オープン MR のクローズ完了');
  } catch (e) {
    console.error('[globalSetup] MR クローズ中にエラー:', e);
  } finally {
    await apiContext.dispose();
  }
}

export default globalSetup;
