import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, effectScope, ref } from 'vue'
import { flushPromises } from '@vue/test-utils'

import { useVisualTools } from '@/composables/useVisualTools'
import type { Article, MediaAsset } from '@/types/business'

const mocks = vi.hoisted(() => ({
  api: {
    generateImage: vi.fn(),
    transformImage: vi.fn(),
    articleMedia: vi.fn(),
    selectMedia: vi.fn(),
    detachMedia: vi.fn(),
    setMediaCover: vi.fn(),
    searchMedia: vi.fn(),
    imageModels: vi.fn(),
  },
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))
vi.mock('@/api/workflow', () => ({ workflowApi: mocks.api }))
vi.mock('element-plus', () => ({ ElMessage: mocks.message }))
vi.mock('@/api/client', () => ({
  getApiErrorMessage: (_error: unknown, fallback: string) => fallback,
}))

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: Error) => void
  const promise = new Promise<T>((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}
const asset = (id: number, articleId: number) =>
  ({ id, articleId, usageType: 'BODY' }) as MediaAsset
const article = (id: number) => ({ id, title: `Article ${id}`, topic: 'test' }) as Article
const cleanup: Array<() => void> = []

function setup() {
  const selectedArticleId = ref<number | undefined>(1)
  const media = ref([asset(11, 1)])
  const scope = effectScope()
  const tools = scope.run(() =>
    useVisualTools({
      selectedArticleId,
      currentVariantId: () => selectedArticleId.value! * 10,
      media,
      previewMedia: computed(() => media.value),
    }),
  )!
  tools.visualPrompt.value = 'A usable image prompt'
  cleanup.push(() => {
    tools.dispose()
    scope.stop()
  })
  function select(id: number) {
    selectedArticleId.value = id
    media.value = [asset(id * 11, id)]
    tools.resetForArticle(article(id), media.value)
  }
  return { tools, selectedArticleId, media, select }
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.api.searchMedia.mockResolvedValue({ items: [], notice: '' })
  mocks.api.generateImage.mockResolvedValue({})
})
afterEach(() => {
  cleanup.splice(0).forEach((dispose) => dispose())
})

describe('visual operations stay attached to their original article context', () => {
  it.each([false, true])(
    'ignores old media refresh, including A -> B -> A (%s)',
    async (returnToA) => {
      const pending = deferred<MediaAsset[]>()
      mocks.api.articleMedia.mockReturnValueOnce(pending.promise)
      const { tools, media, select } = setup()
      const old = tools.generateVisual()
      await flushPromises()
      expect(mocks.api.articleMedia).toHaveBeenCalledWith(1)
      select(2)
      if (returnToA) select(1)
      const current = media.value
      pending.resolve([asset(99, 1)])
      await old
      expect(media.value).toEqual(current)
      expect(tools.visualOperationState.value).toBe('IDLE')
      expect(mocks.message.success).not.toHaveBeenCalled()
    },
  )

  it('old failure/finally cannot replace the progress of a newer operation', async () => {
    const oldResponse = deferred<unknown>(),
      newResponse = deferred<unknown>()
    mocks.api.generateImage
      .mockReturnValueOnce(oldResponse.promise)
      .mockReturnValueOnce(newResponse.promise)
    mocks.api.articleMedia.mockResolvedValue([asset(22, 2)])
    const { tools, select } = setup()
    const old = tools.generateVisual()
    select(2)
    const current = tools.generateVisual()
    oldResponse.reject(new Error('old request failed'))
    await old
    expect(tools.visualLoading.value).toBe(true)
    expect(tools.visualOperationState.value).toBe('RUNNING')
    expect(mocks.message.error).not.toHaveBeenCalled()
    newResponse.resolve({})
    await current
    expect(tools.visualOperationState.value).toBe('SUCCESS')
  })

  it('ignores a completed generation after disposal without starting another media fetch', async () => {
    const response = deferred<unknown>()
    mocks.api.generateImage.mockReturnValueOnce(response.promise)
    const { tools } = setup()
    const pending = tools.generateVisual()
    tools.dispose()
    response.resolve({})
    await pending
    expect(mocks.api.articleMedia).not.toHaveBeenCalled()
    expect(mocks.message.success).not.toHaveBeenCalled()
  })

  it('keeps selection IDs and search provenance when the keyword or article changes', async () => {
    const response = deferred<unknown>()
    mocks.api.searchMedia.mockResolvedValue({
      items: [{ id: 'source-1', imageUrl: 'https://example.org/a.png' }],
      notice: '',
    })
    mocks.api.selectMedia.mockReturnValueOnce(response.promise)
    const { tools, select } = setup()
    tools.visualKeyword.value = 'original keyword'
    await tools.searchVisuals()
    const item = tools.imageSearchResults.value[0]!
    tools.visualKeyword.value = 'edited but not searched'
    const pending = tools.selectVisual(item, 'BODY')
    expect(mocks.api.selectMedia).toHaveBeenCalledWith(
      expect.objectContaining({
        article_id: 1,
        variant_id: 10,
        search_keyword: 'original keyword',
      }),
    )
    select(2)
    response.resolve({})
    await pending
    expect(mocks.api.articleMedia).not.toHaveBeenCalled()
    expect(mocks.message.success).not.toHaveBeenCalled()
  })

  it('does not apply an old cover action or let a stale preview item mutate another article', async () => {
    const response = deferred<unknown>()
    mocks.api.setMediaCover.mockReturnValueOnce(response.promise)
    const { tools, select } = setup()
    const old = tools.setPreviewCover(asset(11, 1))
    select(2)
    response.resolve({})
    await old
    await tools.setPreviewCover(asset(11, 1))
    expect(mocks.api.setMediaCover).toHaveBeenCalledTimes(1)
    expect(mocks.api.articleMedia).not.toHaveBeenCalled()
    expect(mocks.message.success).not.toHaveBeenCalled()
  })
})
