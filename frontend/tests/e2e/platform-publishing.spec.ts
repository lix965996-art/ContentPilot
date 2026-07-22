import { expect, test, type APIRequestContext } from '@playwright/test'

const api = 'http://127.0.0.1:8000/api'

async function adminAuth(request: APIRequestContext) {
  const response = await request.post(`${api}/auth/login`, {
    data: { username: 'admin', password: 'Admin@123456' },
  })
  const body = await response.json()
  return { Authorization: `Bearer ${body.data.access_token}` }
}

let originalModel: Record<string, string | number | boolean> | undefined

test.afterEach(async ({ request }) => {
  if (!originalModel) return
  const headers = await adminAuth(request)
  await request.put(`${api}/settings/model-service`, {
    headers,
    data: {
      provider: originalModel.provider,
      base_url: originalModel.baseUrl,
      api_key: originalModel.apiKey,
      model: originalModel.model,
      input_price_per_million: originalModel.inputPricePerMillion,
      output_price_per_million: originalModel.outputPricePerMillion,
      currency: originalModel.currency,
    },
  })
  originalModel = undefined
})

test('platform account, mock draft, mock publish and manual package workflow', async ({
  page,
  request,
}) => {
  const headers = await adminAuth(request)
  const originalModelResponse = await request.get(`${api}/settings/model-service`, { headers })
  const modelSnapshot = (await originalModelResponse.json()).data
  originalModel = modelSnapshot
  const modelConfig = await request.put(`${api}/settings/model-service`, {
    headers,
    data: {
      provider: 'mock',
      base_url: '',
      api_key: modelSnapshot.apiKey,
      model: 'contentpilot-local',
      input_price_per_million: 0,
      output_price_per_million: 0,
      currency: 'CNY',
    },
  })
  expect(modelConfig.ok()).toBeTruthy()
  const configurations = [
    {
      platform: 'WECHAT_OFFICIAL',
      data: {
        account_name: 'E2E 公众号',
        auth_type: 'APP_SECRET',
        publish_mode: 'MOCK',
        app_id: 'wx-e2e',
      },
    },
    {
      platform: 'WEIBO',
      data: {
        account_name: 'E2E 微博',
        auth_type: 'OAUTH2',
        publish_mode: 'MOCK',
        client_id: 'weibo-e2e',
      },
    },
    {
      platform: 'XIAOHONGSHU',
      data: {
        account_name: 'E2E 小红书',
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
    expect(response.ok()).toBeTruthy()
  }
  const connection = await request.post(`${api}/platform-accounts/WECHAT_OFFICIAL/test`, {
    headers,
  })
  expect(connection.ok()).toBeTruthy()
  expect((await connection.json()).data.status).toBe('CONNECTED')

  const accountResponse = await request.get(`${api}/platform-accounts`, { headers })
  const accounts = (await accountResponse.json()).data
  const accountByPlatform = Object.fromEntries(
    accounts.map((item: { platform: string; id: number }) => [item.platform, item.id]),
  )
  const articleResponse = await request.post(`${api}/articles`, {
    headers,
    data: {
      title: `平台发布 E2E ${Date.now()}`,
      source_text: '这是一篇用于验证平台账号、公众号草稿、微博 Mock 和小红书人工发布包的测试文章。',
      topic: '平台发布测试',
      target_audience: '内容运营人员',
      tone: '专业自然',
      keywords: ['平台账号', '发布测试'],
    },
  })
  expect(articleResponse.ok()).toBeTruthy()
  const articleId = (await articleResponse.json()).data.id
  const generated = await request.post(`${api}/generation/content`, {
    headers,
    data: {
      article_id: articleId,
      platforms: ['WECHAT_OFFICIAL', 'WEIBO', 'XIAOHONGSHU'],
      preserve_meaning: 90,
    },
  })
  const generatedBody = await generated.json()
  expect(generated.ok(), JSON.stringify(generatedBody)).toBeTruthy()
  await expect
    .poll(async () => {
      const taskResponse = await request.get(
        `${api}/generation/tasks/${generatedBody.data.taskId}`,
        { headers },
      )
      return (await taskResponse.json()).data.status
    })
    .toMatch(/SUCCESS|PARTIAL_SUCCESS/)
  const variantResponse = await request.get(`${api}/articles/${articleId}/variants`, { headers })
  const variants = (await variantResponse.json()).data
  const variantByPlatform = Object.fromEntries(
    variants.map((item: { platform: string; id: number }) => [item.platform, item.id]),
  )

  const scheduleIds: Record<string, number> = {}
  const modeByPlatform: Record<string, string> = {
    WECHAT_OFFICIAL: 'MOCK',
    WEIBO: 'MOCK',
    XIAOHONGSHU: 'MANUAL_CONFIRM',
  }
  let offset = 0
  for (const platform of ['WECHAT_OFFICIAL', 'WEIBO', 'XIAOHONGSHU']) {
    const scheduledAt = new Date(Date.now() + (45 * 24 * 60 + offset) * 60_000).toISOString()
    offset += 2
    const created = await request.post(`${api}/schedules`, {
      headers,
      data: {
        article_id: articleId,
        variant_id: variantByPlatform[platform],
        account_id: accountByPlatform[platform],
        platform,
        scheduled_at: scheduledAt,
        publish_mode: modeByPlatform[platform],
      },
    })
    const createdBody = await created.json()
    expect(created.ok(), JSON.stringify(createdBody)).toBeTruthy()
    scheduleIds[platform] = createdBody.data.id
    const published = await request.post(`${api}/schedules/${scheduleIds[platform]}/publish-now`, {
      headers,
    })
    expect(published.ok()).toBeTruthy()
  }

  const wechat = await request.get(`${api}/schedules/${scheduleIds.WECHAT_OFFICIAL}`, { headers })
  expect((await wechat.json()).data.status).toBe('MOCK_DRAFT_CREATED')
  const weibo = await request.get(`${api}/schedules/${scheduleIds.WEIBO}`, { headers })
  expect((await weibo.json()).data.status).toBe('MOCK_SUCCESS')
  const packageResponse = await request.get(
    `${api}/schedules/${scheduleIds.XIAOHONGSHU}/publish-package`,
    { headers },
  )
  expect(packageResponse.ok()).toBeTruthy()
  expect((await packageResponse.json()).data.notice).toContain('人工确认发布')
  const download = await request.get(
    `${api}/schedules/${scheduleIds.XIAOHONGSHU}/publish-package/download`,
    { headers },
  )
  expect(download.headers()['content-type']).toBe('application/zip')
  const confirmed = await request.post(
    `${api}/schedules/${scheduleIds.XIAOHONGSHU}/manual-confirm`,
    {
      headers,
      data: { published_url: 'https://www.xiaohongshu.com/explore/e2e-example' },
    },
  )
  expect((await confirmed.json()).data.status).toBe('MANUAL_PUBLISHED')

  await page.goto('/login')
  await page.getByTestId('username-input').fill('admin')
  await page.getByTestId('password-input').fill('Admin@123456')
  await page.getByTestId('login-button').click()
  await expect(page).toHaveURL('/')
  await page.goto('/platform-accounts')
  await expect(page.getByRole('main').getByRole('heading', { name: '平台账号' })).toBeVisible()
  await expect(page.getByText('E2E 公众号')).toBeVisible()
  await expect(page.getByText('E2E 微博')).toBeVisible()
  await expect(page.getByText('E2E 小红书')).toBeVisible()
  await expect(page.getByText(/不属于服务器无人值守自动发布/)).toBeVisible()

  await page.goto('/publish')
  await page.getByText(`#${scheduleIds.XIAOHONGSHU}`).click()
  await expect(page.getByText('小红书人工发布包', { exact: true })).toBeVisible()
  await expect(page.getByText('MANUAL_CONFIRM').first()).toBeVisible()

  const deletedArticle = await request.delete(`${api}/articles/${articleId}`, { headers })
  expect(deletedArticle.ok()).toBeTruthy()
  for (const platform of ['WECHAT_OFFICIAL', 'WEIBO', 'XIAOHONGSHU']) {
    await request.delete(`${api}/platform-accounts/${platform}`, { headers })
  }
})
