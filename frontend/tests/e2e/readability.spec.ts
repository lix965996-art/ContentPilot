import { expect, test } from '@playwright/test'

// 角色改版后管理员只保留系统页面，业务页面归运营者，因此按角色分组巡检。
const pagesByRole: Array<{ username: string; password: string; pages: string[] }> = [
  {
    username: 'operator',
    password: 'Operator@123456',
    pages: [
      '/',
      '/articles',
      '/studio',
      '/media',
      '/recommendation',
      '/calendar',
      '/publish',
      '/analytics',
      '/experiments',
    ],
  },
  { username: 'admin', password: 'Admin@123456', pages: ['/', '/platform-accounts', '/settings'] },
]

for (const { username, password, pages } of pagesByRole) {
  test(`application text keeps a readable minimum size for ${username}`, async ({ page }) => {
    test.setTimeout(90_000)
    await page.setViewportSize({ width: 1366, height: 768 })
    await page.goto('/login')
    await page.getByTestId('username-input').fill(username)
    await page.getByTestId('password-input').fill(password)
    await page.getByTestId('login-button').click()
    await expect(page).toHaveURL('/')

    for (const path of pages) {
      await page.goto(path)
      await page.waitForLoadState('domcontentloaded')
      const tooSmall = await page.locator('.app-workspace').evaluate((root) =>
        Array.from(root.querySelectorAll<HTMLElement>('*'))
          .filter((element) => {
            const style = getComputedStyle(element)
            const ownText = Array.from(element.childNodes)
              .filter((node) => node.nodeType === Node.TEXT_NODE)
              .map((node) => node.textContent?.trim() || '')
              .join('')
            return (
              ownText.length > 0 &&
              style.display !== 'none' &&
              style.visibility !== 'hidden' &&
              Number.parseFloat(style.fontSize) < 11 &&
              element.getBoundingClientRect().width > 0 &&
              element.getBoundingClientRect().height > 0
            )
          })
          .map((element) => ({
            text: element.textContent?.trim().slice(0, 40),
            size: getComputedStyle(element).fontSize,
            className: element.className,
          })),
      )
      expect(tooSmall, `${path} contains undersized visible text`).toEqual([])
    }
  })
}
