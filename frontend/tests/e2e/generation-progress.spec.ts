import { expect, test } from '@playwright/test'

async function login(page: import('@playwright/test').Page) {
  await page.goto('/login')
  await page.getByTestId('username-input').fill('operator')
  await page.getByTestId('password-input').fill('Operator@123456')
  await page.getByTestId('login-button').click()
  await expect(page).toHaveURL('/')
}

test('studio displays independent real-time progress for all three platforms', async ({ page }) => {
  await login(page)
  let taskPolls = 0
  await page.route('**/api/generation/content', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        message: '生成任务已创建',
        data: { taskId: 'progress-e2e-task', status: 'PENDING' },
      }),
    })
  })
  await page.route('**/api/generation/tasks/progress-e2e-task', async (route) => {
    taskPolls += 1
    const completed = taskPolls >= 4
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        message: 'success',
        data: {
          id: 'progress-e2e-task',
          articleId: 1,
          status: completed ? 'SUCCESS' : 'RUNNING',
          progress: completed ? 100 : 45,
          platformsJson: ['WEIBO', 'XIAOHONGSHU', 'WECHAT_OFFICIAL'],
          resultVariantIdsJson: [],
          variants: [],
          provider: 'test-transport',
          modelName: 'contentpilot-local',
          promptVersion: '2.0.0',
          tokenUsage: completed ? 360 : 0,
          durationMs: completed ? 420 : 0,
          platformStatusJson: {
            WEIBO: {
              status: completed ? 'SUCCESS' : 'RUNNING',
              progress: completed ? 100 : 35,
              stage: completed ? 'COMPLETED' : 'REQUESTING_MODEL',
              message: completed ? '平台版本已生成' : '已发送请求，等待模型生成内容',
              attempt: 1,
              durationMs: 120,
              tokenUsage: 120,
            },
            XIAOHONGSHU: {
              status: completed ? 'SUCCESS' : 'RETRYING',
              progress: completed ? 100 : 65,
              stage: completed ? 'COMPLETED' : 'REQUESTING_MODEL',
              message: completed ? '平台版本已生成' : '第 2 次请求模型修正输出',
              attempt: 2,
              durationMs: 140,
              tokenUsage: 120,
            },
            WECHAT_OFFICIAL: {
              status: completed ? 'SUCCESS' : 'PENDING',
              progress: completed ? 100 : 0,
              stage: completed ? 'COMPLETED' : 'QUEUED',
              message: completed ? '平台版本已生成' : '已进入队列，等待开始处理',
              attempt: completed ? 1 : 0,
              durationMs: 160,
              tokenUsage: 120,
            },
          },
        },
      }),
    })
  })

  await page.goto('/studio')
  await page.getByRole('button', { name: '生成平台版本' }).click()
  await expect(page.getByTestId('generation-progress')).toBeVisible()
  await expect(page.getByTestId('platform-progress-WEIBO')).toContainText('等待模型生成内容')
  await expect(page.getByTestId('platform-progress-XIAOHONGSHU')).toContainText('自动重试')
  await expect(page.getByTestId('platform-progress-XIAOHONGSHU')).toContainText('第 2 次尝试')
  await expect(page.getByTestId('platform-progress-WECHAT_OFFICIAL')).toContainText('排队中')
  await expect(page.getByTestId('generation-wait-hint')).toContainText('自动修正并重试')
  await expect(page.getByTestId('generation-progress')).toContainText('全部完成', {
    timeout: 5_000,
  })
  await expect(page.getByTestId('generation-progress')).toContainText('进度按真实处理阶段计算')
  await expect(page.getByTestId('style-control')).toBeVisible()
  await expect(page.getByTestId('length-control')).toBeVisible()
  await expect(page.getByTestId('preserve-control')).toBeVisible()
})

test('WeChat version opens the formatting assistant and previews a selected theme', async ({
  page,
}) => {
  await login(page)
  await page.goto('/studio')
  await page.locator('.preview-tabs button').filter({ hasText: '微信公众号' }).click()

  await expect(page.getByTestId('open-wechat-formatter')).toBeVisible()
  await page.getByTestId('open-wechat-formatter').click()
  await expect(page.getByTestId('wechat-formatter')).toBeVisible()
  await expect(page.getByRole('button', { name: /清爽简约/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /品牌强调/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /杂志阅读/ })).toBeVisible()

  await page.getByRole('button', { name: /品牌强调/ }).click()
  await expect(
    page.locator('.wechat-rich-content [data-contentpilot-format="wechat-brand"]'),
  ).toBeVisible()
  await page.getByRole('button', { name: '保存并用于发布' }).click()
  await expect(page.getByText('公众号排版已保存，发布草稿时会使用此样式')).toBeVisible()
})
