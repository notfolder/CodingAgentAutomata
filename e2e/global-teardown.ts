/**
 * Playwright グローバルティアダウン
 *
 * 全テスト実行後に RabbitMQ の tasks キューをパージし、
 * 次回実行へのタスク持ち越しを防ぐ。
 * テストが作ったユーザーも消し、次回の実行に残さない。
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

// テストが作るユーザーの名前の接頭辞（users.spec.ts と gitlab_integration.spec.ts が作る）
const TEST_USER_PREFIXES = ['e2e-test-user-', 'e2e-dup-', 'disabled-user-'];

/**
 * テストが作ったユーザーを、名前の接頭辞で探して backend の API で消す。
 * 残ると管理画面のユーザー一覧が埋まり、次の回のテストの結果が変わるため。
 */
async function deleteTestUsers(): Promise<void> {
  const baseURL = process.env.BASE_URL ?? 'http://frontend:80';
  const adminUsername = process.env.ADMIN_USERNAME ?? 'admin';
  const adminPassword = process.env.ADMIN_PASSWORD ?? 'Admin@123456';

  const apiContext = await request.newContext({ baseURL });
  try {
    const login = await apiContext.post('/api/auth/login', {
      data: { username: adminUsername, password: adminPassword },
    });
    if (login.status() !== 200) {
      console.log(`[globalTeardown] テスト用ユーザーの片付け: 管理者ログイン失敗 status=${login.status()} (無視)`);
      return;
    }
    const token = ((await login.json()) as { access_token: string }).access_token;
    const headers = { Authorization: `Bearer ${token}` };

    // 消すと一覧の並びが詰まるので、名前を先に全部集めてから消す
    const targets: string[] = [];
    for (const prefix of TEST_USER_PREFIXES) {
      for (let page = 1; ; page++) {
        const resp = await apiContext.get('/api/users', { headers, params: { search: prefix, page } });
        if (resp.status() !== 200) break;
        const body = (await resp.json()) as { items: Array<{ username: string }>; total: number; per_page: number };
        targets.push(...body.items.map((u) => u.username).filter((name) => name.startsWith(prefix)));
        if (page * body.per_page >= body.total) break;
      }
    }

    let deleted = 0;
    for (const username of targets) {
      const resp = await apiContext.delete(`/api/users/${username}`, { headers });
      if (resp.status() === 204) {
        deleted++;
      } else {
        console.log(`[globalTeardown] テスト用ユーザー ${username} の削除: status=${resp.status()} (無視)`);
      }
    }
    console.log(`[globalTeardown] テスト用ユーザーを削除しました: ${deleted}件`);
  } catch (e) {
    console.log('[globalTeardown] テスト用ユーザーの片付けに失敗しました（無視）:', e);
  } finally {
    await apiContext.dispose();
  }
}

async function globalTeardown(): Promise<void> {
  await purgeRabbitMQQueue();
  await deleteTestUsers();
}

export default globalTeardown;
