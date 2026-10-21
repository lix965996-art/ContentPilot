import { expect, test } from '@playwright/test'

async function login(page: import('@playwright/test').Page, username: string, password: string) {
  await page.goto('/login')
  await page.getByTestId('username-input').fill(username)
  await page.getByTestId('password-input').fill(password)
  await page.getByTestId('login-button').click()
  await expect(page).toHaveURL('/')
}

test('operator sees published interactions without internal model diagnostics', async ({
  page,
}) => {
  await login(page, 'operator', 'Operator@123456')
  const response = page.waitForResponse(
    (r) => r.url().endsWith('/api/learning/status') && r.status() === 200,
  )
  await page.goto('/analytics')
  await response
  const panel = page.getByRole('region', { name: '发布互动' })
  await expect(panel).toBeVisible()
  await expect(panel.getByText('已发布内容的互动')).toBeVisible()
  await expect(panel.getByText(/24小时合格样本|模型与公开数据实验/)).toHaveCount(0)
  await panel.getByRole('button', { name: '刷新互动数据' }).click()
  await expect(panel.getByText('已发布内容的互动')).toBeVisible()
})

test('administrator has model management and read-only users cannot collect', async ({ page }) => {
  await login(page, 'admin', 'Admin@123456')
  await page.goto('/settings')
  await page.getByRole('tab', { name: '高级数据管理' }).click()
  const panel = page.getByRole('region', { name: '发布互动' })
  await expect(panel.getByText(/尚无本地训练模型/)).toBeVisible()
  await expect(panel.getByText('24小时合格样本')).toBeVisible()
  await expect(panel.getByRole('button', { name: '采集最新互动' })).toHaveCount(0)
})
