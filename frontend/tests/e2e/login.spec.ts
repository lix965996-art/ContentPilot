import { expect, test } from '@playwright/test'

async function login(page: import('@playwright/test').Page, username: string, password: string) {
  await page.goto('/login')
  await page.getByTestId('username-input').fill(username)
  await page.getByTestId('password-input').fill(password)
  await page.getByTestId('login-button').click()
  await expect(page).toHaveURL('/')
}

test('administrator can login and open the dashboard', async ({ page }) => {
  await login(page, 'admin', 'Admin@123456')
  await expect(page.getByText('内容资产')).toBeVisible()
  await expect(page.getByText('最近互动趋势')).toBeVisible()
})

test('operator can open the real content workflow pages', async ({ page }) => {
  await login(page, 'operator', 'Operator@123456')
  await page.getByRole('link', { name: '内容管理' }).click()
  await expect(page.getByRole('heading', { name: '内容库' })).toBeVisible()
  await expect(page.getByText('还没有原文')).toBeVisible()
  await page.getByRole('link', { name: '内容适配' }).click()
  await expect(page.getByRole('heading', { name: '平台内容适配' })).toBeVisible()
  await page.getByRole('link', { name: '排期日历' }).click()
  await expect(page.locator('.fc')).toBeVisible()
})

test('operator is denied by the administrator API', async ({ request }) => {
  const loginResponse = await request.post('http://127.0.0.1:8000/api/auth/login', {
    data: { username: 'operator', password: 'Operator@123456' },
  })
  expect(loginResponse.ok()).toBeTruthy()
  const loginBody = await loginResponse.json()
  const response = await request.get('http://127.0.0.1:8000/api/admin/users', {
    headers: { Authorization: `Bearer ${loginBody.data.access_token}` },
  })
  expect(response.status()).toBe(403)
})
