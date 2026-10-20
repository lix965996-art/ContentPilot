import { fireEvent, render, screen, waitFor, within } from '@testing-library/vue'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ArticlesPage from '@/pages/ArticlesPage.vue'
import { workflowApi } from '@/api/workflow'
import type { Article } from '@/types/business'

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: { create: '1' } }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ canManageBusiness: true }) }))
vi.mock('@/api/workflow', () => ({
  workflowApi: {
    articles: vi.fn(),
    articlesEngagement: vi.fn(),
    createArticle: vi.fn(),
    updateArticle: vi.fn(),
  },
}))
vi.mock('element-plus', async (original) => ({
  ...(await original<typeof import('element-plus')>()),
  ElMessage: { warning: vi.fn(), error: vi.fn(), success: vi.fn() },
}))

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(workflowApi.articles).mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    pageSize: 20,
  })
})

async function prepareNewArticle() {
  render(ArticlesPage, { global: { plugins: [ElementPlus] } })
  const dialog = await screen.findByRole('dialog', { name: '新建内容' })
  await fireEvent.update(within(dialog).getAllByRole('textbox')[0], '新文章')
  const body = dialog.querySelectorAll('textarea')[1]
  if (!body) throw new Error('Article body editor is missing')
  await fireEvent.update(body, '这是一段足够长的原文内容，用于验证保存互斥。')
  return within(dialog).getByRole('button', { name: '保存内容' }) as HTMLButtonElement
}

describe('article creation saving state', () => {
  it('submits once while the first save is pending', async () => {
    const pending = deferred<Article>()
    vi.mocked(workflowApi.createArticle).mockReturnValueOnce(pending.promise)
    const save = await prepareNewArticle()
    await fireEvent.click(save)
    await fireEvent.click(save)
    expect(workflowApi.createArticle).toHaveBeenCalledOnce()
    expect(save.disabled).toBe(true)
    pending.resolve({ id: 9 } as Article)
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '新建内容' })).toBeNull())
    expect(workflowApi.articles).toHaveBeenCalledTimes(2)
  })

  it('restores the save control and keeps the form after a failed save', async () => {
    const pending = deferred<Article>()
    vi.mocked(workflowApi.createArticle)
      .mockReturnValueOnce(pending.promise)
      .mockResolvedValueOnce({ id: 10 } as Article)
    const save = await prepareNewArticle()
    await fireEvent.click(save)
    expect(save.disabled).toBe(true)
    pending.reject(new Error('temporarily unavailable'))
    await waitFor(() => expect(save.disabled).toBe(false))
    const dialog = screen.getByRole('dialog', { name: '新建内容' })
    expect(within(dialog).getByDisplayValue('新文章')).toBeTruthy()
    await fireEvent.click(save)
    await waitFor(() => expect(workflowApi.createArticle).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '新建内容' })).toBeNull())
  })
})
