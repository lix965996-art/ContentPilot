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
  await page.getByRole('link', { name: '内容库' }).click()
  await expect(page.getByRole('heading', { name: '内容库' })).toBeVisible()
  await expect(page.getByText('内容库还是空的')).toBeVisible()
  await page.getByRole('link', { name: '内容工作室' }).click()
  await expect(page.getByRole('heading', { name: '内容工作室' })).toBeVisible()
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

test('viewer only sees navigation entries allowed by RBAC', async ({ page }) => {
  await login(page, 'viewer', 'Viewer@123456')

  await expect(page.getByRole('link', { name: '工作台' })).toBeVisible()
  await expect(page.getByRole('link', { name: '内容库' })).toBeVisible()
  await expect(page.getByRole('link', { name: '排期日历' })).toBeVisible()
  await expect(page.getByRole('link', { name: '数据复盘' })).toBeVisible()

  await expect(page.getByRole('link', { name: '内容工作室' })).toHaveCount(0)
  await expect(page.getByRole('link', { name: '媒体库' })).toHaveCount(0)
  await expect(page.getByRole('link', { name: '发布时间' })).toHaveCount(0)
  await expect(page.getByRole('link', { name: '发布任务' })).toHaveCount(0)
  await expect(page.getByRole('link', { name: '实验分析' })).toHaveCount(0)
  await expect(page.getByRole('link', { name: '系统设置' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: /新建内容/ })).toHaveCount(0)

  await page.goto('/settings')
  await expect(page.getByText('当前账号无权访问')).toBeVisible()
})
