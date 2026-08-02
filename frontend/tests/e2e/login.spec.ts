import { expect, test } from '@playwright/test'

const apiBaseUrl = `http://127.0.0.1:${process.env.E2E_API_PORT ?? '8001'}`

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

test('visitor can register an operator account and enter the workspace', async ({ page }) => {
  await page.goto('/register')
  await page.getByTestId('display-name-input').fill('毕业设计体验者')
  await page.getByTestId('username-input').fill('graduation_guest')
  await page.getByTestId('email-input').fill('graduation-guest@example.com')
  await page.getByTestId('password-input').fill('Content123')
  await page.getByTestId('confirm-password-input').fill('Content123')
  await page.getByTestId('register-button').click()

  await expect(page).toHaveURL('/')
  await expect(page.getByRole('complementary').getByText('毕业设计体验者')).toBeVisible()
  await expect(page.getByRole('button', { name: /新建内容/ })).toBeVisible()
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
  await page.getByRole('link', { name: '平台账号' }).click()
  await expect(page.getByText(/当前为运营者只读视图/)).toBeVisible()
  await expect(page.getByRole('button', { name: /编辑配置/ })).toHaveCount(0)
  await expect(page.getByRole('button', { name: /退出登录/ })).toHaveCount(0)
})

test('operator is denied by the administrator API', async ({ request }) => {
  const loginResponse = await request.post(`${apiBaseUrl}/api/auth/login`, {
    data: { username: 'operator', password: 'Operator@123456' },
  })
  expect(loginResponse.ok()).toBeTruthy()
  const loginBody = await loginResponse.json()
  const response = await request.get(`${apiBaseUrl}/api/admin/users`, {
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
