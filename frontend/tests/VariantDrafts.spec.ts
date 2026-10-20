import { afterEach, describe, expect, it, vi } from 'vitest'
import { reactive, ref } from 'vue'
import { useVariantDrafts, type VariantDraftPayload } from '@/composables/useVariantDrafts'
import type { Variant } from '@/types/business'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}
const variant = (id: number, text = `版本${id}`) =>
  ({
    id,
    title: `标题${id}`,
    contentText: text,
    hashtagsJson: [],
    platform: 'WEIBO',
    versionNo: id,
    articleId: 1,
    wordCount: text.length,
    modelName: 'test',
    promptVersion: 'test',
    generationDurationMs: 0,
    tokenUsage: 0,
    promptTokens: 0,
    completionTokens: 0,
    estimatedCost: 0,
    qualityScore: 0,
    manualEditRatio: 0,
    reviewStatus: 'PENDING',
    createdAt: '2030-01-01T00:00:00Z',
  }) satisfies Variant
function setup(update: (id: number, payload: VariantDraftPayload) => Promise<Variant>) {
  const current = ref<Variant>(variant(1))
  const editing = reactive({ title: '', content_text: '', hashtags: [] as string[] })
  const drafts = useVariantDrafts({
    current,
    editing,
    update,
    fromVariant: (value) => ({
      title: value.title,
      content_text: value.contentText,
      hashtags: value.hashtagsJson,
    }),
    onSaved: (value) => {
      if (current.value.id === value.id) {
        current.value = value
        drafts.syncCurrent()
      }
    },
    errorMessage: () => '保存失败',
  })
  drafts.syncCurrent()
  return { current, editing, drafts }
}
const local = (id: number) =>
  JSON.parse(localStorage.getItem(`contentpilot_studio_draft:${id}`) || 'null')

afterEach(() => vi.useRealTimers())

describe('version draft saving', () => {
  it('serializes slow saves and never replaces newer typing with an older response', async () => {
    const first = deferred<Variant>()
    const second = deferred<Variant>()
    const update = vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const { editing, drafts } = setup(update)
    editing.content_text = '先发出的稿子'
    const saving = drafts.save()
    await Promise.resolve()
    editing.content_text = '请求期间继续写的新稿子'
    expect(local(1).content_text).toBe('请求期间继续写的新稿子')
    expect(update).toHaveBeenCalledTimes(1)
    first.resolve(variant(1, '先发出的稿子'))
    await Promise.resolve()
    await Promise.resolve()
    expect(editing.content_text).toBe('请求期间继续写的新稿子')
    expect(local(1).content_text).toBe('请求期间继续写的新稿子')
    expect(update).toHaveBeenCalledTimes(2)
    expect(update.mock.calls[1][1].content_text).toBe('请求期间继续写的新稿子')
    second.resolve(variant(1, '请求期间继续写的新稿子'))
    expect(await saving).toBe(true)
    expect(drafts.saved.value).toBe(true)
    expect(local(1)).toBeNull()
    drafts.dispose()
  })

  it('keeps both versions immediately when switching before the autosave debounce', () => {
    vi.useFakeTimers()
    const update = vi.fn()
    const { current, editing, drafts } = setup(update)
    editing.content_text = '第一版未提交草稿'
    current.value = variant(2)
    drafts.syncCurrent()
    editing.content_text = '第二版未提交草稿'
    current.value = variant(1)
    drafts.syncCurrent()
    expect(editing.content_text).toBe('第一版未提交草稿')
    expect(local(1).content_text).toBe('第一版未提交草稿')
    expect(local(2).content_text).toBe('第二版未提交草稿')
    drafts.dispose()
    vi.runAllTimers()
    expect(update).not.toHaveBeenCalled()
  })

  it('keeps the latest draft when an older save fails after a version switch', async () => {
    const request = deferred<Variant>()
    const { current, editing, drafts } = setup(() => request.promise)
    editing.content_text = '旧快照'
    const saving = drafts.save()
    await Promise.resolve()
    editing.content_text = '较新草稿'
    current.value = variant(2)
    drafts.syncCurrent()
    request.reject(new Error('offline'))
    expect(await saving).toBe(false)
    expect(editing.content_text).toBe('版本2')
    expect(local(1).content_text).toBe('较新草稿')
    current.value = variant(1)
    drafts.syncCurrent()
    expect(editing.content_text).toBe('较新草稿')
    expect(drafts.autosaveState.value).toBe('ERROR')
    drafts.dispose()
  })

  it('protects the last edit on unmount while an earlier response is in flight', async () => {
    const request = deferred<Variant>()
    const update = vi.fn(() => request.promise)
    const { editing, drafts } = setup(update)
    editing.content_text = '已发出'
    const saving = drafts.save()
    await Promise.resolve()
    editing.content_text = '离开页面前的新稿'
    drafts.dispose()
    request.resolve(variant(1, '已发出'))
    expect(await saving).toBe(false)
    expect(local(1).content_text).toBe('离开页面前的新稿')
    expect(update).toHaveBeenCalledTimes(1)
  })

  it('offers the correct version recovery draft after a reload', () => {
    localStorage.setItem(
      'contentpilot_studio_draft:1',
      JSON.stringify({
        variantId: 1,
        savedAt: 1,
        title: '恢复标题',
        content_text: '本地草稿',
        hashtags: ['话题'],
      }),
    )
    const { editing, drafts } = setup(vi.fn())
    expect(editing.content_text).toBe('版本1')
    expect(drafts.recoveryDraft.value?.variantId).toBe(1)
    expect(drafts.restore()).toBe(true)
    expect(editing.content_text).toBe('本地草稿')
    expect(drafts.saved.value).toBe(false)
    drafts.dispose()
  })
})
