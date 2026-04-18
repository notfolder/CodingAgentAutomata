import { defineConfig } from '@playwright/test';

/**
 * Playwright E2Eテスト設定
 * テスト実行: docker compose run --rm test_playwright sh -c "npm install && npx playwright test"
 */
export default defineConfig({
  testDir: './tests',
  timeout: 60000,
  retries: 1,
  use: {
    // docker-compose 内では frontend サービス名でアクセス
    baseURL: process.env.BASE_URL ?? 'http://frontend:80',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    // headless モードで実行
    headless: true,
  },
  reporter: [['html', { open: 'never' }], ['list']],
});
