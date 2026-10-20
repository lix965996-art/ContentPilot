import { expect, test } from '@playwright/test'

test('content library paginates, resets filters and opens an older search result', async ({
  page,
}) => {
  await page.goto('/login')
  await page.getByTestId('username-input').fill('operator')
  await page.getByTestId('password-input').fill('Operator@123456')
  await page.getByTestId('login-button').click()
  await expect(page).toHaveURL('/')
  const marker = `内容分页-${Date.now()}`
  const ids = await page.evaluate(async (title) => {
    const token =
      localStorage.getItem('contentpilot_access_token') ||
      sessionStorage.getItem('contentpilot_access_token')
    const ids: number[] = []
    for (let i = 0; i < 23; i++) {
      const response = await fetch('/api/articles', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: `${title}-${String(i).padStart(2, '0')}`,
          source_text: '用于隔离浏览器回归的文章正文，不涉及任何真实业务数据。',
        }),
      })
      if (!response.ok) throw new Error('Could not create isolated pagination fixture')
      ids.push((await response.json()).data.id)
    }
    return ids
  }, marker)
  try {
    let variantRequests = 0
    page.on('request', (request) => {
      if (/\/api\/articles\/\d+\/variants$/.test(request.url())) variantRequests++
    })
    await page.goto('/articles')
    const keyword = page.getByPlaceholder('搜索标题或正文')
    await keyword.fill(marker)
    const filtered = page.waitForResponse(
      (response) =>
        response.url().includes('/api/articles?') &&
        new URL(response.url()).searchParams.get('keyword') === marker,
    )
    await keyword.press('Enter')
    await filtered
    await expect(page.locator('.content-row')).toHaveCount(20)
    await page.getByTestId('article-pagination').getByRole('button', { name: '下一页' }).click()
    await expect(page.locator('.content-row')).toHaveCount(3)
    await keyword.fill(`${marker}-22`)
    await keyword.press('Enter')
    await expect(page.locator('.content-row')).toHaveCount(1)
    await expect(page.locator('.content-summary')).toContainText(`${marker}-22`)
    expect(variantRequests).toBe(0)
    await page.goto(`/articles?edit=${ids[0]}`)
    const editor = page.getByRole('dialog')
    await expect(editor.getByText('编辑原文', { exact: true })).toBeVisible()
    await expect(editor.getByRole('textbox').first()).toHaveValue(`${marker}-00`)
  } finally {
    if (!page.isClosed())
      await page
        .evaluate(async (articleIds) => {
          const token =
            localStorage.getItem('contentpilot_access_token') ||
            sessionStorage.getItem('contentpilot_access_token')
          for (const id of articleIds)
            await fetch(`/api/articles/${id}`, {
              method: 'DELETE',
              headers: { Authorization: `Bearer ${token}` },
            })
        }, ids)
        .catch(() => {
          /* The disposable API database is reset on the next run. */
        })
  }
})
