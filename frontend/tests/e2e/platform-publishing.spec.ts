import { expect, test, type APIRequestContext } from '@playwright/test'

const api = 'http://127.0.0.1:8000/api'

async function adminAuth(request: APIRequestContext) {
  const response = await request.post(`${api}/auth/login`, {
    data: { username: 'admin', password: 'Admin@123456' },
  })
  const body = await response.json()
  return { Authorization: `Bearer ${body.data.access_token}` }
}

test('real platform modes never report a simulated connection or publish result', async ({
  page,
  request,
}) => {
  const headers = await adminAuth(request)
  const configurations = [
    {
      platform: 'WECHAT_OFFICIAL',
      data: {
        account_name: 'E2E 公众号（待官方验证）',
        auth_type: 'APP_SECRET',
        publish_mode: 'DRAFT_ONLY',
        app_id: 'wx-e2e-unverified',
        app_secret: 'e2e-wechat-secret',
      },
    },
    {
      platform: 'WEIBO',
      data: {
        account_name: 'E2E 微博（待 OAuth）',
        auth_type: 'OAUTH2',
        publish_mode: 'REAL_API',
        client_id: 'weibo-e2e-unverified',
        app_secret: 'e2e-weibo-secret',
      },
    },
    {
      platform: 'XIAOHONGSHU',
      data: {
        account_name: 'E2E 小红书（人工发布）',
        auth_type: 'NONE',
        publish_mode: 'MANUAL_CONFIRM',
      },
    },
  ]
  for (const item of configurations) {
    const response = await request.put(`${api}/platform-accounts/${item.platform}`, {
      headers,
      data: item.data,
    })
    expect(response.ok(), await response.text()).toBeTruthy()
  }

  const accountResponse = await request.get(`${api}/platform-accounts`, { headers })
  const accounts = (await accountResponse.json()).data
  const byPlatform = Object.fromEntries(
    accounts.map((item: { platform: string; id: number; status: string }) => [item.platform, item]),
  )
  expect(byPlatform.WEIBO.status).toBe('CONNECTING')
  expect(byPlatform.WECHAT_OFFICIAL.status).toBe('CONNECTING')
  expect(byPlatform.XIAOHONGSHU.status).toBe('MANUAL_ONLY')

  const articlesResponse = await request.get(`${api}/articles?page_size=100`, { headers })
  const articles = (await articlesResponse.json()).data.items
  let articleId = 0
  let variants: Array<{ platform: string; id: number }> = []
  for (const article of articles) {
    const response = await request.get(`${api}/articles/${article.id}/variants`, { headers })
    const rows = (await response.json()).data
    if (new Set(rows.map((item: { platform: string }) => item.platform)).size === 3) {
      articleId = article.id
      variants = rows
      break
    }
  }
  expect(articleId).toBeGreaterThan(0)
  const variantByPlatform = Object.fromEntries(
    variants.map((item: { platform: string; id: number }) => [item.platform, item.id]),
  )

  for (const [platform, mode] of [
    ['WEIBO', 'REAL_API'],
    ['WECHAT_OFFICIAL', 'DRAFT_ONLY'],
  ] as const) {
    const rejected = await request.post(`${api}/schedules`, {
      headers,
      data: {
        article_id: articleId,
        variant_id: variantByPlatform[platform],
        account_id: byPlatform[platform].id,
        platform,
        scheduled_at: new Date(Date.now() + 45 * 24 * 60 * 60_000).toISOString(),
        publish_mode: mode,
      },
    })
    expect(rejected.status()).toBe(400)
    expect((await rejected.json()).code).toBe(40075)
  }

  const manualSchedule = await request.post(`${api}/schedules`, {
    headers,
    data: {
      article_id: articleId,
      variant_id: variantByPlatform.XIAOHONGSHU,
      account_id: byPlatform.XIAOHONGSHU.id,
      platform: 'XIAOHONGSHU',
      scheduled_at: new Date(Date.now() + 46 * 24 * 60 * 60_000).toISOString(),
      publish_mode: 'MANUAL_CONFIRM',
    },
  })
  expect(manualSchedule.ok()).toBeTruthy()
  const scheduleId = (await manualSchedule.json()).data.id
  const published = await request.post(`${api}/schedules/${scheduleId}/publish-now`, { headers })
  expect((await published.json()).data.status).toBe('WAITING_MANUAL_CONFIRM')
  const packageResponse = await request.get(`${api}/schedules/${scheduleId}/publish-package`, {
    headers,
  })
  expect((await packageResponse.json()).data.creatorUrl).toContain('creator.xiaohongshu.com')

  await page.goto('/login')
  await page.getByTestId('username-input').fill('admin')
  await page.getByTestId('password-input').fill('Admin@123456')
  await page.getByTestId('login-button').click()
  await expect(page).toHaveURL('/')
  await page.goto('/platform-accounts')
  await expect(page.getByText('E2E 公众号（待官方验证）')).toBeVisible()
  await expect(page.getByText('E2E 微博（待 OAuth）')).toBeVisible()
  await expect(page.getByText('仅人工交付')).toBeVisible()
  await expect(page.getByText(/Mock/i)).toHaveCount(0)

  const deletedSchedule = await request.delete(`${api}/schedules/${scheduleId}`, { headers })
  expect(deletedSchedule.ok()).toBeTruthy()
  for (const platform of ['WECHAT_OFFICIAL', 'WEIBO', 'XIAOHONGSHU']) {
    await request.delete(`${api}/platform-accounts/${platform}`, { headers })
  }
})
