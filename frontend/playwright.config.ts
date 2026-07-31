import { defineConfig, devices } from '@playwright/test'

const apiPort = Number(process.env.E2E_API_PORT || 8001)
const webPort = Number(process.env.E2E_WEB_PORT || 5174)
const apiUrl = `http://127.0.0.1:${apiPort}`
const webUrl = `http://127.0.0.1:${webPort}`

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  // E2E cases share a disposable SQLite database that is never reused by the dev server.
  workers: 1,
  retries: 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: webUrl,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], channel: 'chromium' },
    },
  ],
  webServer: [
    {
      command: '..\\backend\\.venv\\Scripts\\python.exe ..\\backend\\app\\tests\\e2e_server.py',
      env: {
        APP_DEMO_MODE: 'true',
        APP_ENV: 'test',
        DATABASE_URL: 'sqlite:///./app/tests/.e2e_socialflow.db',
        E2E_API_PORT: String(apiPort),
        JWT_SECRET: 'e2e-secret-that-is-long-enough-for-jwt-signing',
      },
      url: `${apiUrl}/api/health`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: 'npm run dev',
      env: {
        CONTENTPILOT_API_TARGET: apiUrl,
        CONTENTPILOT_WEB_PORT: String(webPort),
      },
      url: webUrl,
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
})
