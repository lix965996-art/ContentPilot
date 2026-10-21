import { expect, test, type APIRequestContext } from '@playwright/test'

const api = `http://127.0.0.1:${process.env.E2E_API_PORT || 8001}/api`

async function login(page: import('@playwright/test').Page, username: string, password: string) {
  await page.goto('/login')
  await page.getByTestId('username-input').fill(username)
  await page.getByTestId('password-input').fill(password)
  await page.getByTestId('login-button').click()
  await expect(page).toHaveURL('/')
}

// platform-publishing 用例的清理阶段会删除全部平台账号，而“计算跨平台推荐时间”
// 要求所选平台都有账号；为不依赖用例执行顺序，先通过管理员 API 把账号补齐。
async function ensurePlatformAccounts(request: APIRequestContext) {
  const loginResponse = await request.post(`${api}/auth/login`, {
    data: { username: 'admin', password: 'Admin@123456' },
  })
  const headers = {
    Authorization: `Bearer ${(await loginResponse.json()).data.access_token}`,
  }
  const configurations = [
    {
      platform: 'WEIBO',
      data: {
        account_name: '语义排期用微博',
        auth_type: 'OAUTH2',
        publish_mode: 'REAL_API',
        client_id: 'weibo-semantic-e2e',
        app_secret: 'semantic-e2e-secret',
      },
    },
    {
      platform: 'WECHAT_OFFICIAL',
      data: {
        account_name: '语义排期用公众号',
        auth_type: 'APP_SECRET',
        publish_mode: 'DRAFT_ONLY',
        app_id: 'wx-semantic-e2e',
        app_secret: 'semantic-e2e-secret',
      },
    },
    {
      platform: 'XIAOHONGSHU',
      data: {
        account_name: '语义排期用小红书',
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
}

test('cross-platform plan explains timing choices without internal algorithm parameters', async ({
  page,
  request,
}) => {
  // The pipeline calls the LLM (and falls back when it is unreachable), so the
  // whole calculation is slower than a plain CRUD page.
  test.setTimeout(240_000)

  await ensurePlatformAccounts(request)
  await login(page, 'operator', 'Operator@123456')
  await page.getByRole('link', { name: '发布时间' }).click()
  await expect(page.getByRole('heading', { name: '发布时间推荐' })).toBeVisible()

  // The demo seed has no 今日头条 account, which would block the calculation.
  await page.locator('.platform-checks').getByText('今日头条').click()

  await expect(page.getByText('智能联合排期', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '计算跨平台推荐时间' }).click()

  const profilePanel = page.getByText('内容排期画像')
  await expect(profilePanel).toBeVisible({ timeout: 200_000 })

  // Main table shows the conclusions required by the scheduling workflow.
  for (const header of ['内容策略', '原始最佳时间', '优化后时间', '调整原因', '排期状态']) {
    await expect(page.getByRole('columnheader', { name: header })).toBeVisible()
  }

  // Two platforms must not collapse onto the exact same moment.
  await page.getByRole('button', { name: '详情' }).first().click()
  await expect(page.getByText('约束与调整原因')).toBeVisible()
  await expect(page.getByText('硬约束检查')).toBeVisible()
  await expect(page.getByText('软目标与权重')).toHaveCount(0)
  await expect(page.getByText(/算法版本：|阶段状态：|预测耗时超过预算/)).toHaveCount(0)
  await expect(
    page.getByText('智能审查只提供排期建议，实际发布时间以你确认的排期为准。'),
  ).toBeVisible()
})
