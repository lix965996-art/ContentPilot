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
