import { expect, test } from '@playwright/test'

async function login(page: import('@playwright/test').Page, username: string, password: string) {
  await page.goto('/login')
  await page.getByTestId('username-input').fill(username)
  await page.getByTestId('password-input').fill(password)
  await page.getByTestId('login-button').click()
  await expect(page).toHaveURL('/')
}

test('primary navigation actions respond for an operator', async ({ page }) => {
  await login(page, 'operator', 'Operator@123456')

  await page.getByRole('button', { name: '搜索' }).click()
  const searchDialog = page.locator('.command-dialog')
  await expect(searchDialog).toBeVisible()
  await searchDialog.getByPlaceholder('搜索页面或内容').fill('内容库')
  await searchDialog.getByRole('button', { name: '内容库' }).click()
  await expect(page).toHaveURL(/\/articles/)

  await page
    .getByRole('main')
    .getByRole('button', { name: /新建内容/ })
    .click()
  await expect(page.getByRole('dialog').getByText('新建内容', { exact: true })).toBeVisible()
  await page.getByRole('dialog').getByRole('button', { name: '取消' }).click()

  await page.getByRole('button', { name: '通知' }).click()
  await expect(
    page.getByText(/暂无新事项|个版本待审核|条内容待排期|条发布失败/).first(),
  ).toBeVisible()

  await page.goto('/studio')
  await page.getByTitle('定位到正文').click()
  await page.getByTitle('选择图片').click()
  await expect(page).toHaveURL(/\/media\?article=/)
})

test('studio edits are automatically saved and survive reload', async ({ page }) => {
  await login(page, 'operator', 'Operator@123456')
  await page.goto('/studio')

  const editor = page.locator('.editor-content')
  await expect(editor).toBeVisible()
  const original = await editor.inputValue()
  const marker = `自动保存验收-${Date.now()}`
  const savedRequest = page.waitForResponse(
    (response) =>
      response.request().method() === 'PUT' &&
      /\/api\/variants\/\d+$/.test(response.url()) &&
      response.ok(),
  )
  await editor.fill(`${original}\n\n${marker}`)
  await savedRequest
  await expect(page.getByText('已自动保存', { exact: true })).toBeVisible()

  await page.reload()
  await expect(editor).toHaveValue(new RegExp(marker))
})

test('a selected preview image can be removed without deleting the asset', async ({ page }) => {
  await login(page, 'operator', 'Operator@123456')
  const fixture = await page.evaluate(async () => {
    const token =
      localStorage.getItem('contentpilot_access_token') ||
      sessionStorage.getItem('contentpilot_access_token')
    const headers = {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    }
    const articleResponse = await fetch('/api/articles?page_size=1', { headers })
    const articleBody = await articleResponse.json()
    const articleId = articleBody.data.items[0].id as number
    const altText = `可移除配图-${Date.now()}`
    const selectedResponse = await fetch('/api/media/select', {
      method: 'POST',
      headers,
      body: JSON.stringify({
        article_id: articleId,
        source: 'E2E',
        source_id: altText,
        image_url:
          'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="200" height="120"%3E%3Crect width="100%25" height="100%25" fill="%236b8afd"/%3E%3C/svg%3E',
        thumbnail_url:
          'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="200" height="120"%3E%3Crect width="100%25" height="100%25" fill="%236b8afd"/%3E%3C/svg%3E',
        alt_text: altText,
        usage_type: 'COVER',
      }),
    })
    const selectedBody = await selectedResponse.json()
    return { articleId, altText, assetId: selectedBody.data.id as number }
  })

  await page.goto(`/studio?article=${fixture.articleId}`)
  const image = page.getByAltText(fixture.altText)
  await expect(image).toBeVisible()
  const detached = page.waitForResponse(
    (response) =>
      response.request().method() === 'POST' &&
      response.url().endsWith(`/api/media/${fixture.assetId}/detach`) &&
      response.ok(),
  )
  await image
    .locator('..')
    .getByRole('button', { name: `移除图片：${fixture.altText}` })
    .click()
  await detached
  await expect(image).toHaveCount(0)
  await expect(page.getByText('图片已移除，可以重新选择')).toBeVisible()
})

test('viewer sees read-only actions instead of operations that return 403', async ({ page }) => {
  await login(page, 'viewer', 'Viewer@123456')

  await page.goto('/articles')
  await page.locator('.content-summary').first().click()
  const articleDialog = page.getByRole('dialog')
  await expect(articleDialog.getByText('查看原文', { exact: true })).toBeVisible()
  await expect(articleDialog.getByRole('button', { name: '保存内容' })).toHaveCount(0)
  await articleDialog.getByRole('button', { name: '关闭', exact: true }).click()

  await page.goto('/calendar')
  await expect(page.getByRole('button', { name: '新建排期' })).toHaveCount(0)

  await page.goto('/analytics')
  await expect(page.getByRole('button', { name: '手工录入' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '导入数据' })).toHaveCount(0)
})
