import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import ElementPlus, { ElMessage } from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MediaPage from '@/pages/MediaPage.vue'
import { workflowApi } from '@/api/workflow'
import type { Article, MediaAsset } from '@/types/business'

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: { article: '1' } }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/api/workflow', () => ({
  workflowApi: {
    articles: vi.fn(),
    mediaAssets: vi.fn(),
    articleMedia: vi.fn(),
    keywords: vi.fn(),
    searchMedia: vi.fn(),
    attachMedia: vi.fn(),
    selectMedia: vi.fn(),
    uploadMedia: vi.fn(),
    updateMedia: vi.fn(),
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

function asset(id: number): MediaAsset {
  return {
    id,
    title: `素材-${id}`,
    thumbnailUrl: '',
    imageUrl: '',
    altText: '',
    favorite: false,
  } as MediaAsset
}

function renderPage() {
  return render(MediaPage, {
    global: {
      plugins: [ElementPlus],
      stubs: {
        ElSelect: {
          props: ['modelValue', 'disabled'],
          emits: ['update:modelValue', 'change'],
          methods: {
            choose(event: Event) {
              const raw = (event.target as HTMLSelectElement).value
              const value = /^\d+$/.test(raw) ? Number(raw) : raw
              this.$emit('update:modelValue', value)
              this.$emit('change', value)
            },
          },
          template:
            '<select :value="modelValue" :disabled="disabled" @change="choose"><slot /></select>',
        },
        ElOption: {
          props: ['value', 'label'],
          template: '<option :value="value">{{ label }}</option>',
        },
      },
    },
  })
}

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(workflowApi.articles).mockResolvedValue({
    items: [
      { id: 1, title: '文章 A' },
      { id: 2, title: '文章 B' },
    ] as Article[],
    total: 2,
    page: 1,
    pageSize: 100,
  })
  vi.mocked(workflowApi.mediaAssets).mockResolvedValue({ items: [], collections: [], total: 0 })
})

describe('media page article context', () => {
  it('ignores a late response from the previous article', async () => {
    const firstA = deferred<MediaAsset[]>()
    const b = deferred<MediaAsset[]>()
    const secondA = deferred<MediaAsset[]>()
    vi.mocked(workflowApi.articleMedia)
      .mockReturnValueOnce(firstA.promise)
      .mockReturnValueOnce(b.promise)
      .mockReturnValueOnce(secondA.promise)

    renderPage()
    await waitFor(() => expect(workflowApi.articleMedia).toHaveBeenCalledTimes(1))
    const select = screen.getByRole('combobox')

    await fireEvent.update(select, '2')
    await waitFor(() => expect(workflowApi.articleMedia).toHaveBeenCalledTimes(2))
    b.resolve([asset(2)])
    await screen.findByText('1 张已关联')

    firstA.resolve([asset(1), asset(11)])
    await firstA.promise
    await waitFor(() => expect(screen.getByText('1 张已关联')).toBeTruthy())

    await fireEvent.update(select, '1')
    await waitFor(() => expect(workflowApi.articleMedia).toHaveBeenCalledTimes(3))
    secondA.resolve([asset(1), asset(11), asset(12)])
    await screen.findByText('3 张已关联')
  })

  it('does not surface a stale error after switching articles', async () => {
    const firstA = deferred<MediaAsset[]>()
    const b = deferred<MediaAsset[]>()
    vi.mocked(workflowApi.articleMedia)
      .mockReturnValueOnce(firstA.promise)
      .mockReturnValueOnce(b.promise)

    renderPage()
    await waitFor(() => expect(workflowApi.articleMedia).toHaveBeenCalledTimes(1))
    const select = screen.getByRole('combobox')
    await fireEvent.update(select, '2')
    await waitFor(() => expect(workflowApi.articleMedia).toHaveBeenCalledTimes(2))
    b.resolve([asset(2)])
    await screen.findByText('1 张已关联')

    firstA.reject(new Error('late A failure'))
    await firstA.promise.catch(() => undefined)
    await waitFor(() => expect(ElMessage.error).not.toHaveBeenCalled())
  })
})
