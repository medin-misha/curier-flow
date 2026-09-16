import { defineConfig, devices } from '@playwright/test'
const live = process.env.E2E_LIVE === '1'
export default defineConfig({
  testDir: './tests',
  testMatch: live ? 'live.spec.ts' : 'site.spec.ts',
  timeout: 90_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: 'list',
  use: { baseURL: process.env.E2E_BASE_URL || 'http://127.0.0.1:3000', ignoreHTTPSErrors: true, trace: 'retain-on-failure' },
  projects: live ? [{ name: 'live-chromium', use: { ...devices['Desktop Chrome'] } }] : [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 1000 } } },
    { name: 'mobile', use: { ...devices['iPhone 13'], defaultBrowserType: 'chromium' } },
  ],
  webServer: process.env.E2E_BASE_URL ? undefined : { command: 'npm run dev -- --strictPort', url: 'http://127.0.0.1:3000', reuseExistingServer: true },
})
