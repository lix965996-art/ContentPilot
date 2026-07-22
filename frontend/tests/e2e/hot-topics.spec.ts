import { expect, test } from '@playwright/test'

async function login(page: import('@playwright/test').Page) {
  await page.goto('/login')
  await page.getByTestId('username-input').fill('operator')
  await page.getByTestId('password-input').fill('Operator@123456')
  await page.getByTestId('login-button').click()
  await expect(page).toHaveURL('/')
}

test('a real-source trend angle enters deep creation mode', async ({ page }) => {
  await login(page)
  await page.route('**/api/trends?**', (route) =>
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        message: 'success',
        data: {
          items: [
            {
              id: 'BAIDU-1',
              source: 'BAIDU',
              sourceName: '百度热榜',
              rank: 1,
              title: '内容行业热点测试',
              summary: '来自公开榜单的摘要',
              url: 'https://example.com/source',
              heatLabel: '10000 热度',
              fetchedAt: new Date().toISOString(),
              tags: ['内容行业'],
            },
          ],
          sources: [{ source: 'BAIDU', name: '百度热榜', status: 'SUCCESS', count: 1 }],
          fetchedAt: new Date().toISOString(),
          notice: '全部内容来自公开实时榜单。',
        },
      }),
    }),
  )
  await page.route('**/api/trends/analyze', (route) =>
    new Promise((resolve) => globalThis.setTimeout(resolve, 800)).then(() =>
      route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          message: 'success',
          data: {
            relevance_reason: '适合讨论内容运营变化',
            recommended_angle_index: 0,
            angles: [
              {
                title: '热点背后的内容变化',
                audience: '内容运营者',
                hook: '从一个热点看行业变化',
                outline: ['核验热点事实', '分析内容趋势'],
                creative_goal: '引发讨论',
              },
              {
                title: '如何审慎追热点',
                audience: '新媒体编辑',
                hook: '速度之外更需要核验',
                outline: ['信息来源', '发布边界'],
                creative_goal: '知识分享',
              },
            ],
            risk_notes: ['不要把榜单摘要当作完整新闻'],
            verification_questions: ['原始来源是否支持核心结论？'],
            provider: 'test-provider',
            modelName: 'test-model',
            tokenUsage: 320,
          },
        }),
      }),
    ),
  )
  await page.route('**/api/articles', async (route) => {
    if (route.request().method() !== 'POST') return route.continue()
    return route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ code: 0, message: 'success', data: { id: 41 } }),
    })
  })

  await page.goto('/trends')
  await expect(page.getByText('内容行业热点测试')).toBeVisible()
  await page.getByRole('button', { name: 'AI 分析选题' }).click()
  await expect(page.getByTestId('trend-analysis-loading')).toContainText('真实模型')
  await expect(page.getByText('热点背后的内容变化')).toBeVisible()
  await page.getByRole('button', { name: '用这个角度进入深度创作' }).click()
  await expect(page).toHaveURL(/\/studio\?article=41&mode=deep/)
  await expect(page.getByTestId('generation-mode-control').getByText('深度创作')).toBeVisible()
})

test('trend analysis failure shows a retry action instead of an empty drawer', async ({ page }) => {
  await login(page)
  await page.route('**/api/trends?**', (route) =>
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        message: 'success',
        data: {
          items: [
            {
              id: 'BAIDU-2',
              source: 'BAIDU',
              sourceName: '百度热榜',
              rank: 2,
              title: '超时处理测试',
              summary: '公开摘要',
              url: 'https://example.com/source',
              heatLabel: '上榜',
              fetchedAt: new Date().toISOString(),
              tags: [],
            },
          ],
          sources: [{ source: 'BAIDU', name: '百度热榜', status: 'SUCCESS', count: 1 }],
          fetchedAt: new Date().toISOString(),
          notice: '真实来源',
        },
      }),
    }),
  )
  await page.route('**/api/trends/analyze', (route) =>
    route.fulfill({
      status: 504,
      contentType: 'application/json',
      body: JSON.stringify({ code: 50401, message: '模型响应超时，请稍后重试', data: null }),
    }),
  )
  await page.goto('/trends')
  await page.getByRole('button', { name: 'AI 分析选题' }).click()
  await expect(page.getByTestId('trend-analysis-error')).toContainText('模型响应超时')
  await expect(page.getByRole('button', { name: '重新分析' })).toBeVisible()
})
