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
  timeout: 300000,
  // Consumer はシングルスレッドで1タスクずつ処理するため、
  // 並列実行するとキューが詰まり TASK_TIMEOUT_MS（120秒）でタイムアウトする。
  // シリアル実行（workers=1）でキューバックログを防ぐ。
  workers: 1,
  retries: 1,
  globalSetup: './global-setup.ts',
  globalTeardown: './global-teardown.ts',
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
