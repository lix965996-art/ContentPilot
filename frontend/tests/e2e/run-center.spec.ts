import { expect, test } from '@playwright/test'

async function login(page: import('@playwright/test').Page) {
  await page.goto('/login')
  await page.getByTestId('username-input').fill('operator')
  await page.getByTestId('password-input').fill('Operator@123456')
  await page.getByTestId('login-button').click()
  await expect(page).toHaveURL('/')
}

async function loginAs(page: import('@playwright/test').Page, username: 'admin' | 'operator') {
  await page.goto('/login')
  await page.getByTestId('username-input').fill(username)
  await page
    .getByTestId('password-input')
    .fill(username === 'admin' ? 'Admin@123456' : 'Operator@123456')
  await page.getByTestId('login-button').click()
  await expect(page).toHaveURL('/')
}

const technicalPublishError =
  '素材上传失败 [48001]: api unauthorized rid: 6a61f59f-61d639c8-35cad9be. 请配置默认封面素材 ID (default_cover_media_id)，或在文章中选择一张本地图片作为封面；mode=DRAFT_ONLY; external_id=—'

async function mockFailedPublish(page: import('@playwright/test').Page) {
  await page.route('**/api/operation-runs**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        message: 'success',
        data: {
          summary: { total: 1, running: 0, failed: 1, success: 0 },
          items: [
            {
              id: 'publish:93',
              sourceId: 93,
              type: 'PUBLISH',
              title: '那些没说出口的话，时间都替我们记得',
              subtitle: 'WECHAT_OFFICIAL · ContentPilot 公众号',
              status: 'FAILED',
              progress: 100,
              durationMs: 241,
              errorMessage: technicalPublishError,
              createdAt: '2026-07-23T19:06:03',
              updatedAt: '2026-07-23T19:06:04',
              retryCount: 1,
              maxRetryCount: 3,
              steps: [
                {
                  key: 'publish',
                  name: 'PUBLISH',
                  status: 'FAILED',
                  stage: 'FAILED',
                  message: technicalPublishError,
                  error: technicalPublishError,
                  progress: 100,
                  durationMs: 241,
                  attempt: 1,
                },
              ],
            },
          ],
        },
      }),
    })
  })
}

test('run center presents readable records and opens a detailed execution drawer', async ({
  page,
}) => {
  await login(page)
  await page.route('**/api/operation-runs**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        message: 'success',
        data: {
          summary: { total: 2, running: 1, failed: 1, success: 0 },
          items: [
            {
              id: 'generation:run-center-test',
              sourceId: 'run-center-test',
              type: 'GENERATION',
              title: 'AI 内容运营复盘',
              subtitle: 'WEIBO、X、WECHAT_OFFICIAL',
              status: 'PARTIAL_SUCCESS',
              progress: 67,
              provider: 'siliconflow',
              modelName: 'Qwen/Qwen3.6-35B-A3B',
              tokenUsage: 1560,
              durationMs: 42600,
              errorMessage: '微博生成结果未通过格式校验',
              createdAt: '2026-07-30T09:30:00',
              updatedAt: '2026-07-30T09:31:00',
              steps: [
                {
                  key: 'WEIBO',
                  name: 'WEIBO',
                  status: 'FAILED',
                  stage: 'VALIDATING',
                  message: '结构化输出校验失败',
                  progress: 100,
                  durationMs: 18200,
                  tokenUsage: 620,
                  error: '正文超过平台限制',
                  attempt: 2,
                },
                {
                  key: 'X',
                  name: 'X',
                  status: 'SUCCESS',
                  stage: 'COMPLETED',
                  message: '平台版本已生成',
                  progress: 100,
                  durationMs: 11400,
                  tokenUsage: 410,
                  attempt: 1,
                },
                {
                  key: 'WECHAT_OFFICIAL',
                  name: 'WECHAT_OFFICIAL',
                  status: 'SUCCESS',
                  stage: 'COMPLETED',
                  message: '平台版本已生成',
                  progress: 100,
                  durationMs: 13000,
                  tokenUsage: 530,
                  attempt: 1,
                },
              ],
            },
            {
              id: 'publish:run-center-test',
              sourceId: 8,
              type: 'PUBLISH',
              title: '今日热点观察',
              subtitle: 'X · ContentPilot X',
              status: 'PUBLISHING',
              progress: 55,
              durationMs: 3200,
              createdAt: '2026-07-30T10:00:00',
              updatedAt: '2026-07-30T10:00:03',
              retryCount: 0,
              maxRetryCount: 3,
              steps: [],
            },
          ],
        },
      }),
    })
  })

  await page.goto('/runs')

  await expect(page.getByRole('heading', { name: '运行记录' })).toBeVisible()
  await expect(page.getByText('需要处理').first()).toBeVisible()
  await expect(page.getByText('成功率 0%')).toBeVisible()
  await expect(page.getByText('微博').first()).toBeVisible()
  await expect(page.getByText('微信公众号').first()).toBeVisible()
  await expect(page.getByText('WECHAT_OFFICIAL')).toHaveCount(0)

  await page.getByRole('button', { name: '查看运行记录：AI 内容运营复盘' }).click()
  await expect(page.getByRole('heading', { name: 'AI 内容运营复盘' })).toBeVisible()
  await expect(page.getByText('模型服务')).toBeVisible()
  await expect(page.getByText('执行步骤').last()).toBeVisible()
  await expect(page.getByText('处理完成').first()).toBeVisible()
  await expect(page.getByText('COMPLETED')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '仅重试该平台' })).toBeVisible()
})

test('operator sees a clear publishing fix instead of backend error details', async ({ page }) => {
  await loginAs(page, 'operator')
  await mockFailedPublish(page)
  await page.goto('/runs')

  await page
    .getByRole('button', {
      name: '查看运行记录：那些没说出口的话，时间都替我们记得',
    })
    .click()

  await expect(page.getByRole('heading', { name: '公众号素材接口未授权' })).toBeVisible()
  await expect(page.getByText('公众号授权可能已失效')).toBeVisible()
  await expect(page.getByRole('button', { name: '前往平台账号设置' })).toBeVisible()
  await expect(page.getByRole('button', { name: '检查封面素材' })).toBeVisible()
  await expect(page.getByText('api unauthorized')).toHaveCount(0)
  await expect(page.getByText('default_cover_media_id')).toHaveCount(0)
  await expect(page.getByText(/查看技术详情/)).toHaveCount(0)
  await expect(page.getByRole('button', { name: '从失败处重新发布' })).toHaveCount(0)
})

test('administrator can expand technical details when troubleshooting', async ({ page }) => {
  await loginAs(page, 'admin')
  await mockFailedPublish(page)
  await page.goto('/runs')

  await page
    .getByRole('button', {
      name: '查看运行记录：那些没说出口的话，时间都替我们记得',
    })
    .click()

  const details = page.locator('.run-technical-details')
  await expect(details).toBeVisible()
  await expect(details.locator('pre')).toBeHidden()
  await details.getByText('查看技术详情（仅管理员）').click()
  await expect(details.locator('pre')).toContainText('api unauthorized')
  await expect(details.locator('pre')).toContainText('default_cover_media_id')
})
