import { expect, test } from '@playwright/test'

test('administrator can configure the real optional Toutiao entry safely', async ({ page }) => {
  await page.goto('/login')
  await page.getByTestId('username-input').fill('admin')
  await page.getByTestId('password-input').fill('Admin@123456')
  await page.getByTestId('login-button').click()
  await expect(page).toHaveURL('/')
  await page.goto('/platform-accounts')

  const card = page.getByTestId('platform-account-TOUTIAO')
  await expect(card).toBeVisible()
  await expect(card).toContainText('今日头条')
  await expect(card).toContainText('尚未登录今日头条创作中心')

  await card.getByRole('button', { name: '编辑配置' }).click()
  await expect(page.getByText('本机 Chrome 扫码登录与真实文章发布')).toBeVisible()
  await expect(
    page.getByText('安全模式：可以扫码和检测登录，但不会向今日头条发送文章。'),
  ).toBeVisible()
  await expect(page.getByRole('button', { name: '保存并获取登录二维码' })).toBeVisible()
})
