import { defineConfig, devices } from '@playwright/test'
import { randomBytes } from 'node:crypto'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const projectRoot = fileURLToPath(new URL('..', import.meta.url))
const varDirectory = resolve(projectRoot, process.env.CONTENTPILOT_VAR_DIR?.trim() || 'var')
const e2eDirectory = resolve(varDirectory, 'run/e2e')
const apiPort = Number(process.env.E2E_API_PORT || 8001)
const webPort = Number(process.env.E2E_WEB_PORT || 5174)
const apiUrl = `http://127.0.0.1:${apiPort}`
const webUrl = `http://127.0.0.1:${webPort}`
// Ephemeral per-run secret: the E2E server only lives for this test session.
const e2eJwtSecret = process.env.E2E_JWT_SECRET?.trim() || randomBytes(32).toString('hex')

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  // E2E cases share a disposable SQLite database that is never reused by the dev server.
  workers: 1,
  retries: 0,
  outputDir: resolve(varDirectory, 'reports/playwright/results'),
  reporter: [
    ['list'],
    ['html', { open: 'never', outputFolder: resolve(varDirectory, 'reports/playwright/html') }],
  ],
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
        CONTENTPILOT_VAR_DIR: e2eDirectory,
        PYTHONDONTWRITEBYTECODE: '1',
        E2E_API_PORT: String(apiPort),
        JWT_SECRET: e2eJwtSecret,
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
        CONTENTPILOT_VAR_DIR: e2eDirectory,
      },
      url: webUrl,
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
})
