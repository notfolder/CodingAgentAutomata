/**
 * Playwright グローバルセットアップ
 *
 * 全テスト実行前に GitLab のオープン MR をすべてクローズし、
 * テスト間のデータ混入（waitForMR が過去のMRを掴む問題）を防ぐ。
 */

import { request } from '@playwright/test';

async function globalSetup(): Promise<void> {
  const GITLAB_API_URL = process.env.GITLAB_API_URL ?? 'http://gitlab:8929';
  const GITLAB_ADMIN_TOKEN = process.env.GITLAB_ADMIN_TOKEN ?? '';
  const GITLAB_PROJECT_ID = process.env.GITLAB_PROJECT_ID ?? '';

  if (!GITLAB_ADMIN_TOKEN || !GITLAB_PROJECT_ID) {
    console.log('[globalSetup] GITLAB_ADMIN_TOKEN または GITLAB_PROJECT_ID が未設定のためスキップします');
    return;
  }

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
