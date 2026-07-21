import { expect, test } from '@playwright/test'

const pages = [
  '/',
  '/articles',
  '/studio',
  '/media',
  '/recommendation',
  '/calendar',
  '/publish',
  '/analytics',
  '/experiments',
  '/settings',
]

test('application text keeps a readable minimum size', async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 768 })
  await page.goto('/login')
  await page.getByTestId('username-input').fill('admin')
  await page.getByTestId('password-input').fill('Admin@123456')
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
