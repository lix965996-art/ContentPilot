import { expect, test } from '@playwright/test'

async function login(page: import('@playwright/test').Page) {
  await page.goto('/login')
  await page.getByTestId('username-input').fill('operator')
  await page.getByTestId('password-input').fill('Operator@123456')
  await page.getByTestId('login-button').click()
  await expect(page).toHaveURL('/')
}

test('studio desktop columns and platform tabs stay aligned', async ({ page }) => {
  await page.setViewportSize({ width: 2048, height: 1024 })
  await login(page)
  await page.goto('/studio')

  const layout = await page.locator('.composer-shell').evaluate((shell) => {
    const panels = [
      shell.querySelector('.composer-settings'),
      shell.querySelector('.composer-preview'),
      shell.querySelector('.composer-editor'),
    ].filter((panel): panel is Element => Boolean(panel))
    const tabs = [...shell.querySelectorAll('.preview-tabs button')]
    return {
      panelTops: panels.map((panel) => Math.round(panel.getBoundingClientRect().top)),
      panelBottoms: panels.map((panel) => Math.round(panel.getBoundingClientRect().bottom)),
      tabTops: tabs.map((tab) => Math.round(tab.getBoundingClientRect().top)),
      tabBottoms: tabs.map((tab) => Math.round(tab.getBoundingClientRect().bottom)),
      tabOverflow: tabs.map(
        (tab) =>
          (tab as HTMLElement).scrollHeight > (tab as HTMLElement).clientHeight + 1 ||
          (tab as HTMLElement).scrollWidth > (tab as HTMLElement).clientWidth + 1,
      ),
    }
  })

  expect(new Set(layout.panelTops).size).toBe(1)
  expect(new Set(layout.panelBottoms).size).toBe(1)
  expect(new Set(layout.tabTops).size).toBe(1)
  expect(new Set(layout.tabBottoms).size).toBe(1)
  expect(layout.tabOverflow).toEqual([false, false, false, false])
})

test('studio automatically fits an existing illustrated Weibo draft to the publish limit', async ({
  page,
}) => {
  await login(page)
  await page.goto('/studio')
  await page.locator('.preview-tabs button').filter({ hasText: '微博' }).click()

  const preview = page.getByTestId('weibo-platform-preview')
  await expect(preview).toBeVisible()
  if ((await preview.locator('.weibo-media img').count()) > 0) {
    await expect
      .poll(async () => Number(await preview.getAttribute('data-status-length')))
      .toBeLessThanOrEqual(140)
    await expect(preview.locator('.publish-warning')).toHaveCount(0)
    await page.waitForTimeout(1800)
  }
})

test('AI image transform reports measurable progress and completion', async ({ page }) => {
  await login(page)
  await page.route('**/api/media/image-models', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        message: 'ok',
        data: {
          models: ['Qwen/Qwen-Image-Edit-2509'],
          textToImage: [],
          imageToImage: ['Qwen/Qwen-Image-Edit-2509'],
          provider: 'test',
        },
      }),
    })
  })
  await page.route('**/api/articles/*/media', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        message: 'ok',
        data: [
          {
            id: 9001,
            articleId: 52,
            source: 'UPLOADED',
            imageUrl: '/uploads/e2e-source.png',
            thumbnailUrl: '/uploads/e2e-source.png',
            altText: '待改造图片',
            usageType: 'COVER',
            selected: true,
            tags: [],
            favorite: false,
            createdAt: '2026-07-30T00:00:00',
          },
        ],
      }),
    })
  })
  await page.route('**/api/media/transform', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 900))
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 0,
        message: 'ok',
        data: {
          id: 9999,
          articleId: 52,
          source: 'AI_TRANSFORMED',
          sourceId: 'e2e-image.png',
          imageUrl: '/uploads/e2e-image.png',
          thumbnailUrl: '/uploads/e2e-image.png',
          altText: 'AI 改造测试图',
          usageType: 'COVER',
          selected: true,
        },
      }),
    })
  })

  await page.goto('/studio')
  const assistant = page.getByTestId('visual-assistant')
  await assistant.getByText('AI 改造', { exact: true }).click()
  await assistant.locator('textarea').fill('保留主体，改造成简洁的蓝色科技风插画')
  const transformButton = page.getByTestId('visual-transform-button')
  await expect(transformButton).toBeEnabled()
  await transformButton.click()

  const progress = page.getByTestId('visual-operation-progress')
  await expect(progress).toHaveAttribute('data-state', 'RUNNING')
  await expect(progress).toContainText('预计进度')
  await expect(progress).toHaveAttribute('data-state', 'SUCCESS', { timeout: 10_000 })
  await expect(progress).toContainText('100%')
})

test('studio displays independent real-time progress for all four platforms', async ({ page }) => {
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
          platformsJson: ['WEIBO', 'XIAOHONGSHU', 'WECHAT_OFFICIAL', 'X'],
          resultVariantIdsJson: [],
          variants: [],
          provider: 'test-transport',
          modelName: 'contentpilot-local',
          promptVersion: '2.0.0',
          tokenUsage: completed ? 480 : 0,
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
            X: {
              status: completed ? 'SUCCESS' : 'RUNNING',
              progress: completed ? 100 : 50,
              stage: completed ? 'COMPLETED' : 'VALIDATING',
              message: completed ? '平台版本已生成' : '正在校验 X 帖子格式',
              attempt: 1,
              durationMs: 150,
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
  await expect(page.getByTestId('platform-progress-X')).toContainText('正在校验 X 帖子格式')
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

test('X target uses its own post preview instead of falling through to WeChat', async ({
  page,
}) => {
  await login(page)
  await page.goto('/studio')
  await page.locator('.preview-tabs button').filter({ hasText: /^X$/ }).click()

  await expect(page.getByTestId('x-platform-preview')).toBeVisible()
  await expect(page.getByTestId('wechat-platform-preview')).toHaveCount(0)
  await expect(page.getByText(/本地估算，最终以后端 \/ X 校验为准/)).toBeVisible()
})

test('deep creation workbench exposes artifacts and lets the user override AI selection', async ({
  page,
}) => {
  await login(page)

  const task = (userSelectedCandidate?: number) => ({
    id: 'deep-workbench-e2e',
    articleId: 1,
    status: 'SUCCESS',
    progress: 100,
    platformsJson: ['WEIBO'],
    resultVariantIdsJson: userSelectedCandidate === undefined ? [1] : [1, 99],
    variants: [],
    provider: 'test-transport',
    modelName: 'contentpilot-local',
    promptVersion: '2.0.0',
    tokenUsage: 480,
    durationMs: 860,
    optionsJson: { generation_mode: 'DEEP', creative_goal: '知识分享' },
    platformStatusJson: {
      WEIBO: {
        status: 'SUCCESS',
        progress: 100,
        stage: 'COMPLETED',
        message: userSelectedCandidate === undefined ? '平台版本已生成' : '已采用候选稿 2',
        attempt: 2,
        durationMs: 860,
        tokenUsage: 480,
        brief: {
          core_thesis: '深度创作应保留事实边界，并让用户参与关键决策。',
          immutable_facts: ['原文明确包含三个创作步骤'],
          supporting_points: ['用户需要比较不同表达路径'],
          audience_needs: ['理解内容取舍'],
          content_gaps: ['没有提供外部研究来源'],
          forbidden_inferences: ['不得虚构用户数据'],
        },
        strategy: {
          angle: '从用户控制感切入',
          hook: '真正的深度不是多等几十秒',
          reader_value: '看清研究、候选与审校之间的关系',
          structure: ['指出问题', '展示差异', '给出行动'],
          cta: '选择更适合自己的表达',
        },
        candidates: [
          {
            title: '深度创作不是更慢的按钮',
            content: '第一份候选稿强调创作流程的透明度。',
            hashtags: ['#内容创作'],
            warnings: [],
          },
          {
            title: '把创作决定权交还给用户',
            content: '第二份候选稿强调比较、选择和继续编辑。',
            hashtags: ['#创作工作流'],
            warnings: [],
          },
        ],
        candidateTitles: ['深度创作不是更慢的按钮', '把创作决定权交还给用户'],
        selectedCandidate: 0,
        userSelectedCandidate,
        userSelectedVariantId: userSelectedCandidate === undefined ? undefined : 99,
        review: {
          factual_consistency: 96,
          information_completeness: 92,
          platform_fit: 91,
          readability: 94,
          format_compliance: 98,
          non_genericness: 90,
          issues: [],
          improvements: ['保留清晰的人工选择入口'],
        },
      },
    },
  })

  await page.route('**/api/generation/articles/1/latest-deep-task', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ code: 0, message: 'success', data: task() }),
    })
  })
  await page.route(
    '**/api/generation/tasks/deep-workbench-e2e/platforms/WEIBO/select-candidate',
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 0,
          message: '候选稿已保存为新版本',
          data: {
            task: task(1),
            variant: {
              id: 99,
              articleId: 1,
              platform: 'WEIBO',
              versionNo: 2,
              title: '把创作决定权交还给用户',
              contentText: '第二份候选稿强调比较、选择和继续编辑。',
              hashtagsJson: ['#创作工作流'],
              wordCount: 22,
              modelName: 'contentpilot-local',
              promptVersion: '2.0.0',
              generationDurationMs: 0,
              tokenUsage: 0,
              promptTokens: 0,
              completionTokens: 0,
              estimatedCost: 0,
              qualityScore: 92,
              manualEditRatio: 0,
              reviewStatus: 'PENDING',
              createdAt: new Date().toISOString(),
            },
          },
        }),
      })
    },
  )

  await page.goto('/studio?mode=deep')
  await expect(page.getByTestId('deep-creation-workbench')).toBeVisible()
  await page.getByRole('button', { name: '查看过程' }).click()
  await expect(page.getByTestId('deep-creation-workbench')).toContainText('素材研究简报')
  await expect(page.getByTestId('deep-candidate-0')).toContainText('AI 推荐')
  await expect(page.getByTestId('deep-candidate-1')).toContainText('比较、选择和继续编辑')

  await page.getByTestId('select-deep-candidate-1').click()
  await expect(page.getByTestId('deep-candidate-1')).toContainText('你已采用')
  await expect(page.locator('.editor-title')).toHaveValue('把创作决定权交还给用户')
})
