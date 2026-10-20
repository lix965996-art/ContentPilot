import { describe, expect, it, vi } from 'vitest'
import { useGenerationPolling } from '@/composables/useGenerationPolling'
import { generationOutcome, publishOutcome } from '@/utils/task-outcome'
import type { GenerationTask, Schedule, Variant } from '@/types/business'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((yes) => {
    resolve = yes
  })
  return { promise, resolve }
}
const task = (status: GenerationTask['status']) =>
  ({
    id: 'task-1',
    articleId: 1,
    status,
    platformsJson: ['WEIBO'],
    platformStatusJson: {},
    variants: [],
  }) as unknown as GenerationTask

describe('generation polling and terminal notices', () => {
  it('ignores an old task response after switching articles', async () => {
    let articleId = 1
    const response = deferred<GenerationTask>()
    const onTask = vi.fn()
    const fetchVariants = vi.fn()
    const polling = useGenerationPolling({
      articleId: () => articleId,
      fetchTask: () => response.promise,
      fetchVariants,
      onTask,
      onComplete: vi.fn(),
    })
    const waiting = polling.poll('task-1', polling.begin(1))
    articleId = 2
    polling.cancel()
    response.resolve(task('SUCCESS'))
    expect(await waiting).toBeUndefined()
    expect(onTask).not.toHaveBeenCalled()
    expect(fetchVariants).not.toHaveBeenCalled()
  })

  it('does not refill variants from an old article after the terminal refresh returns', async () => {
    let articleId = 1
    const variants = deferred<Variant[]>()
    const onComplete = vi.fn()
    const polling = useGenerationPolling({
      articleId: () => articleId,
      fetchTask: async () => task('SUCCESS'),
      fetchVariants: () => variants.promise,
      onTask: vi.fn(),
      onComplete,
    })
    const waiting = polling.poll('task-1', polling.begin(1))
    await Promise.resolve()
    articleId = 2
    polling.begin(2)
    variants.resolve([])
    await waiting
    expect(onComplete).not.toHaveBeenCalled()
  })

  it.each(['重新生成', '平台重试', '重做候选稿'])(
    'reports FAILED for %s as an error',
    async (success) => {
      const failed = { ...task('FAILED'), errorMessage: '提供商拒绝请求' }
      const polling = useGenerationPolling({
        articleId: () => 1,
        fetchTask: async () => failed,
        fetchVariants: async () => [],
        onTask: vi.fn(),
        onComplete: vi.fn(),
      })
      const result = await polling.poll('task-1', polling.begin(1))
      expect(generationOutcome(result!, success, 'WEIBO')).toEqual({
        type: 'error',
        message: '提供商拒绝请求',
      })
    },
  )

  it('checks a target platform failure even when other platforms succeeded', () => {
    const partial = {
      ...task('PARTIAL_SUCCESS'),
      platformStatusJson: { WEIBO: { status: 'FAILED', error: '当前平台失败' } },
    } as GenerationTask
    expect(generationOutcome(partial, '重试成功', 'WEIBO')).toEqual({
      type: 'error',
      message: '当前平台失败',
    })
    expect(generationOutcome(task('RUNNING'), '已生成').type).toBe('info')
  })

  it('does not call a failed or interrupted publish action a success', () => {
    expect(publishOutcome({ status: 'FAILED', errorMessage: '平台登录过期' } as Schedule)).toEqual({
      type: 'error',
      message: '平台登录过期',
    })
    expect(publishOutcome({ status: 'INTERRUPTED' } as Schedule).type).toBe('warning')
    expect(publishOutcome({ status: 'PUBLISH_SUBMITTED' } as Schedule).type).toBe('info')
    expect(publishOutcome({ status: 'PUBLISHED' } as Schedule).type).toBe('success')
  })
})
