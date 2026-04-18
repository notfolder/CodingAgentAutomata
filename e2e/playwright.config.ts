import { defineConfig } from '@playwright/test';

/**
 * Playwright E2Eテスト設定
 *
 * LLMモックモード（デフォルト）:
 *   docker compose --profile test up -d
 *   docker compose run --rm test_playwright sh -c "npm install && npx playwright test"
 *
 * 実LLMモード（OpenAI/Anthropic APIを実際に呼び出す）:
 *   docker compose --profile test-real up -d
 *   docker compose run --rm test_playwright_real sh -c "npm install && npx playwright test"
 */

// LLM_MODE 環境変数によってレポート出力先を分ける
const llmMode = process.env.LLM_MODE ?? 'mock';

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
  // LLMモードごとにレポートを分割保存する
  reporter: [['html', { open: 'never', outputFolder: `playwright-report/${llmMode}` }], ['list']],
});
