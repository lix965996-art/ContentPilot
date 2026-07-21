import { expect, test } from '@playwright/test'

const pages = [
  ['dashboard', '/'],
  ['content-library', '/articles'],
  ['content-studio', '/studio'],
  ['media-library', '/media'],
  ['publish-time', '/recommendation'],
  ['calendar', '/calendar'],
  ['publish-tasks', '/publish'],
  ['analytics', '/analytics'],
  ['experiments', '/experiments'],
  ['settings', '/settings'],
] as const

for (const viewport of [
  { width: 1366, height: 768, name: '1366x768' },
  { width: 1920, height: 1080, name: '1920x1080' },
]) {
  test(`capture product UI at ${viewport.name}`, async ({ page }) => {
    test.setTimeout(120_000)
    await page.setViewportSize(viewport)
    await page.goto('/login')
    await page.waitForLoadState('networkidle')
    await page.screenshot({ path: `artifacts/ui-audit/${viewport.name}/login.png` })
    await page.getByTestId('username-input').fill('admin')
    await page.getByTestId('password-input').fill('Admin@123456')
    await page.getByTestId('login-button').click()
    await expect(page).toHaveURL('/')
    for (const [name, path] of pages) {
      await page.goto(path)
      await page.waitForLoadState('domcontentloaded')
      await page.waitForTimeout(500)
      await expect
        .poll(() =>
          page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
        )
        .toBe(true)
      await page.screenshot({ path: `artifacts/ui-audit/${viewport.name}/${name}.png` })
    }
  })
}
