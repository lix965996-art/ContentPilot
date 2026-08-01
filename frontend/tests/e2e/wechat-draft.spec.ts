import { expect, test } from '@playwright/test'

async function loginAsAdmin(page: import('@playwright/test').Page) {
  await page.goto('/login')
  await page.getByTestId('username-input').fill('admin')
  await page.getByTestId('password-input').fill('Admin@123456')
  await page.getByTestId('login-button').click()
  await expect(page).toHaveURL('/')
}

test('WeChat account offers local QR draft mode without hiding the official API mode', async ({
  page,
}) => {
  await loginAsAdmin(page)
  await page.goto('/platform-accounts')

  const card = page.getByTestId('platform-account-WECHAT_OFFICIAL')
  await expect(card).toBeVisible()
  await card.getByRole('button', { name: '编辑配置' }).click()

  await expect(page.getByRole('radio', { name: '本机扫码（推荐）' })).toBeVisible()
  await expect(page.getByRole('radio', { name: '官方 API', exact: true })).toBeVisible()
  await page.getByText('本机扫码（推荐）', { exact: true }).click()
  await expect(page.getByRole('button', { name: '保存并获取登录二维码' })).toBeVisible()
  await expect(page.getByText('文章只保存到公众号草稿箱')).toBeVisible()
})

test('WeChat studio variant exposes one-click save-to-draft', async ({ page }) => {
  await loginAsAdmin(page)
  await page.goto('/studio')
  await page.locator('.preview-tabs button').filter({ hasText: '公众号' }).click()

  await expect(page.getByTestId('save-wechat-draft')).toBeVisible()
  await expect(page.getByTestId('save-wechat-draft')).toContainText('存入公众号草稿箱')
})
