import { expect, test } from '@playwright/test'

test('administrator can test a model connection and inspect usage', async ({ page }) => {
  await page.goto('/login')
  await page.getByTestId('username-input').fill('admin')
  await page.getByTestId('password-input').fill('Admin@123456')
  await page.getByTestId('login-button').click()
  await expect(page).toHaveURL('/')

  await page.goto('/settings')
  await page.getByTestId('model-provider').click()
  await page.getByRole('option', { name: '本地规则模型' }).click()
  await page.getByTestId('test-model-connection').click()
  await expect(page.getByText('本地规则模型可用').first()).toBeVisible()

  await page.getByRole('tab', { name: '用量与费用' }).click()
  await expect(page.getByRole('heading', { name: '模型用量' })).toBeVisible()
  await expect(page.getByText('输入 Token')).toBeVisible()
  await expect(page.getByText('输出 Token')).toBeVisible()
  await expect(page.getByText('预估费用', { exact: true })).toBeVisible()
})
