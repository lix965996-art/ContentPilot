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
  await expect(page.getByText('待处理')).toBeVisible()
  await expect(page.getByText('最近内容')).toBeVisible()
  await expect(page.getByText('今日排期')).toBeVisible()
})

test('operator can open the real content workflow pages', async ({ page }) => {
  await login(page, 'operator', 'Operator@123456')
  await page.getByRole('link', { name: '内容库' }).click()
  await expect(page.getByRole('heading', { name: '内容库' })).toBeVisible()
  await expect(page.getByPlaceholder('搜索标题或正文')).toBeVisible()
  await page.getByRole('link', { name: '创作' }).click()
  await expect(page.getByRole('heading', { name: '创作' })).toBeVisible()
  await page.getByRole('link', { name: '日历' }).click()
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
  await expect(page.getByRole('link', { name: '日历' })).toBeVisible()
  await expect(page.getByRole('link', { name: '数据' })).toBeVisible()

  await expect(page.getByRole('link', { name: '创作' })).toHaveCount(0)
  await expect(page.getByRole('link', { name: '媒体' })).toHaveCount(0)
  await expect(page.getByRole('link', { name: '发布时间' })).toHaveCount(0)
  await expect(page.getByRole('link', { name: '发布' })).toHaveCount(0)
  await expect(page.getByRole('link', { name: '实验' })).toHaveCount(0)
  await expect(page.getByRole('link', { name: '设置' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: /新建内容/ })).toHaveCount(0)

  await page.goto('/settings')
  await expect(page.getByText('当前账号无权访问')).toBeVisible()
})
