import { expect, test } from '@playwright/test'

async function login(page: import('@playwright/test').Page) {
  await page.goto('/login')
  await page.getByTestId('username-input').fill('operator')
  await page.getByTestId('password-input').fill('Operator@123456')
  await page.getByTestId('login-button').click()
  await expect(page).toHaveURL('/')
}

test('X configuration sends unconfigured administrators to the developer portal first', async ({
  page,
}) => {
  await page.goto('/login')
  await page.getByTestId('username-input').fill('admin')
  await page.getByTestId('password-input').fill('Admin@123456')
  await page.getByTestId('login-button').click()
  await expect(page).toHaveURL('/')

  await page.goto('/platform-accounts')
  const xCard = page.getByTestId('platform-account-X')
  await expect(xCard).toBeVisible()
  await xCard.getByRole('button', { name: '编辑配置' }).click()

  const developerPortalLink = page.getByTestId('open-x-developer-portal')
  await expect(developerPortalLink).toBeVisible()
  await expect(developerPortalLink).toHaveAttribute('href', /developer\.x\.com/)
  await expect(page.getByTestId('start-x-oauth')).toHaveCount(0)
  await expect(page.getByText('OAuth 2.0 Client ID')).toBeVisible()
})

test('X publish-now requires an explicit second confirmation and never posts during the test', async ({
  page,
}) => {
  await login(page)
  let publishRequests = 0
  const schedule = {
    id: 9001,
    articleId: 1,
    variantId: 1,
    platform: 'X',
    articleTitle: 'X 真实发布安全检查',
    variantTitle: 'X 帖子版本',
    scheduledAt: new Date(Date.now() + 3_600_000).toISOString(),
    accountId: 88,
    accountName: '毕业设计测试账号',
    publishMode: 'REAL_API',
    status: 'PENDING',
    retryCount: 0,
    logs: [],
  }

  await page.route('**/api/schedules**', async (route) => {
    if (route.request().method() === 'POST') {
      publishRequests += 1
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          message: 'success',
          data: { ...schedule, status: 'SUCCESS' },
        }),
      })
      return
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ code: 0, message: 'success', data: [schedule] }),
    })
  })

  await page.goto('/publish')
  await expect(page.getByText('X 真实发布安全检查')).toBeVisible()
  await expect(page.getByText('X 官方 API（真实发布）')).toBeVisible()
  await page.getByRole('button', { name: '立即发布' }).click()

  await expect(page.getByText(/内容可能立即公开可见/)).toBeVisible()
  await page.getByRole('button', { name: '确定' }).click()
  await expect(page.getByText('真实发布二次确认')).toBeVisible()
  await expect(page.getByText(/输入“发布到X”后才能继续/)).toBeVisible()
  await page.getByPlaceholder('发布到X').fill('发布到X')
  await page.getByRole('button', { name: '确认真实发布' }).click()

  await expect.poll(() => publishRequests).toBe(1)
})
