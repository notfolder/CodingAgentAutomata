/**
 * Playwright グローバルティアダウン
 *
 * 全テスト実行後に RabbitMQ の tasks キューをパージし、
 * 次回実行へのタスク持ち越しを防ぐ。
 */

import { request } from '@playwright/test';

async function purgeRabbitMQQueue(): Promise<void> {
  const rabbitmqUser = process.env.RABBITMQ_DEFAULT_USER ?? 'guest';
  const rabbitmqPass = process.env.RABBITMQ_DEFAULT_PASS ?? 'guest';
  const rabbitmqMgmtUrl = process.env.RABBITMQ_MGMT_URL ?? 'http://rabbitmq:15672';
  const queueName = 'tasks';

  const mgmtContext = await request.newContext({ baseURL: rabbitmqMgmtUrl });
  try {
    const auth = Buffer.from(`${rabbitmqUser}:${rabbitmqPass}`).toString('base64');
    const resp = await mgmtContext.delete(
      `/api/queues/%2F/${queueName}/contents`,
      { headers: { Authorization: `Basic ${auth}` } }
    );

    if (resp.status() === 204 || resp.status() === 200) {
      console.log(`[globalTeardown] RabbitMQ キュー "${queueName}" をパージしました`);
    } else {
      console.log(`[globalTeardown] RabbitMQ キューパージ: status=${resp.status()} (無視)`);
    }
  } catch (e) {
    console.log('[globalTeardown] RabbitMQ キューパージに失敗しました（無視）:', e);
  } finally {
    await mgmtContext.dispose();
  }
}

async function globalTeardown(): Promise<void> {
  await purgeRabbitMQQueue();
}

export default globalTeardown;
