import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'
import { useBatchRecommendation } from '@/composables/useBatchRecommendation'
import { workflowApi } from '@/api/workflow'
import { ElMessage } from 'element-plus'
import type {
  BatchRecommendationResponse,
  BatchScheduleResponse,
  Platform,
  PublishTimeRecommendation,
  Variant,
} from '@/types/business'

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn(), info: vi.fn() },
}))
vi.mock('@/api/workflow', () => ({
  workflowApi: {
    recommendBatch: vi.fn(),
    variants: vi.fn(),
    scheduleConflictCheck: vi.fn(),
    createSchedulesBatch: vi.fn(),
  },
}))

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((yes) => {
    resolve = yes
  })
  return { promise, resolve }
}
function response(
  platforms: Platform[] = ['WEIBO', 'XIAOHONGSHU'],
  at = '2030-01-01T10:00:00+08:00',
): BatchRecommendationResponse {
  return {
    articleId: 1,
    successCount: platforms.length,
    failureCount: 0,
    hasOverlap: platforms.length > 1,
    overlapGroups: [platforms],
    items: platforms.map((platform, index) => ({
      platform,
      success: true,
      data: {
        id: index + 1,
        articleId: 1,
        platform,
        recommendedAt: at,
        conflicts: [],
        alternatives: [],
      } as unknown as PublishTimeRecommendation,
    })),
  }
}
function setup() {
  const scope = effectScope()
  const batch = scope.run(() => useBatchRecommendation())!
  batch.articleId.value = 1
  batch.selectedPlatforms.value = ['WEIBO', 'XIAOHONGSHU']
  batch.accountByPlatform.WEIBO = 11
  batch.accountByPlatform.XIAOHONGSHU = 22
  batch.variants.value = [
    { id: 1, platform: 'WEIBO', versionNo: 1 },
    { id: 2, platform: 'XIAOHONGSHU', versionNo: 1 },
  ] as Variant[]
  return { batch, scope }
}

beforeEach(() => {
  vi.resetAllMocks()
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
    callback(0)
    return 0
  })
  vi.mocked(workflowApi.scheduleConflictCheck).mockResolvedValue({
    platform: 'WEIBO',
    scheduledAt: '2030-01-01T10:00:00+08:00',
    hasConflict: false,
    hasDensityWarning: false,
    conflicts: [],
  })
  vi.mocked(workflowApi.recommendBatch).mockResolvedValue(response())
  vi.mocked(workflowApi.createSchedulesBatch).mockResolvedValue({
    successCount: 2,
    failureCount: 0,
    createdScheduleIds: [101, 102],
    items: [
      { platform: 'WEIBO', success: true },
      { platform: 'XIAOHONGSHU', success: true },
    ],
  } as BatchScheduleResponse)
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('batch recommendation request and time locks', () => {
  it('does not invent backend progress while a slow request is pending', async () => {
    vi.useFakeTimers()
    const pending = deferred<BatchRecommendationResponse>()
    vi.mocked(workflowApi.recommendBatch).mockReturnValueOnce(pending.promise)
    const { batch, scope } = setup()
    const calculating = batch.calculateBatch()
    await vi.advanceTimersByTimeAsync(15_000)
    expect(batch.loading.value).toBe(true)
    expect(batch.calcStep.value).toBe(0)
    expect(batch.calcPercent.value).toBe(0)
    pending.resolve(response())
    await calculating
    expect(batch.calcPercent.value).toBe(100)
    scope.stop()
  })

  it('staggering leaves a locked row and its next request lock unchanged', async () => {
    const { batch, scope } = setup()
    await batch.calculateBatch()
    const pinned = batch.planRows.value[1]
    batch.toggleLock(pinned)
    const lockedAt = pinned.selectedAt
    await batch.staggerOverlaps(15)
    expect(pinned.selectedAt).toBe(lockedAt)
    expect(pinned.locked).toBe(true)
    const other = batch.planRows.value[0]
    expect(new Date(other.selectedAt).getTime() - new Date(lockedAt).getTime()).toBe(15 * 60_000)
    vi.mocked(workflowApi.recommendBatch).mockResolvedValueOnce(
      response(undefined, '2030-01-02T10:00:00+08:00'),
    )
    await batch.calculateBatch()
    expect(vi.mocked(workflowApi.recommendBatch).mock.calls[1][0].targets[1].locked_at).toBe(
      lockedAt,
    )
    expect(batch.planRows.value[1].selectedAt).toBe(lockedAt)
    scope.stop()
  })

  it('clears locks on account and article changes and ignores an old recommendation', async () => {
    const { batch, scope } = setup()
    await batch.calculateBatch()
    batch.toggleLock(batch.planRows.value[0])
    batch.accountByPlatform.WEIBO = 99
    await batch.calculateBatch()
    expect(
      vi.mocked(workflowApi.recommendBatch).mock.calls[1][0].targets[0].locked_at,
    ).toBeUndefined()
    batch.toggleLock(batch.planRows.value[0])
    const pending = deferred<BatchRecommendationResponse>()
    vi.mocked(workflowApi.recommendBatch).mockReturnValueOnce(pending.promise)
    const old = batch.calculateBatch()
    batch.articleId.value = 2
    pending.resolve(response())
    await old
    expect(batch.batchResult.value).toBeUndefined()
    expect(batch.planRows.value).toEqual([])
    batch.variants.value = [{ id: 3, platform: 'WEIBO', versionNo: 1 }] as Variant[]
    await batch.calculateBatch()
    expect(
      vi
        .mocked(workflowApi.recommendBatch)
        .mock.calls[3][0].targets.every((target) => !target.locked_at),
    ).toBe(true)
    scope.stop()
  })

  it('ignores old version-list responses after switching articles quickly', async () => {
    const pending = deferred<Variant[]>()
    const { batch, scope } = setup()
    vi.mocked(workflowApi.variants)
      .mockReturnValueOnce(pending.promise)
      .mockResolvedValueOnce([{ id: 222, platform: 'WEIBO', versionNo: 1 }] as Variant[])
    const old = batch.loadVariants()
    batch.articleId.value = 2
    await batch.loadVariants()
    pending.resolve([{ id: 111, platform: 'WEIBO', versionNo: 1 }] as Variant[])
    await old
    expect(batch.variants.value[0].id).toBe(222)
    scope.stop()
  })

  it('does not overwrite the conflict result for a newer time with an older response', async () => {
    const { batch, scope } = setup()
    await batch.calculateBatch()
    const row = batch.planRows.value[0]
    const oldConflict = deferred<Awaited<ReturnType<typeof workflowApi.scheduleConflictCheck>>>()
    vi.mocked(workflowApi.scheduleConflictCheck).mockReturnValueOnce(oldConflict.promise)
    const checking = batch.refreshRowConflict(row)
    batch.applyAlternative(row, '2030-01-01T12:00:00+08:00')
    await Promise.resolve()
    oldConflict.resolve({
      platform: 'WEIBO',
      scheduledAt: '2030-01-01T10:00:00+08:00',
      hasConflict: true,
      hasDensityWarning: false,
      conflicts: [],
    })
    await checking
    expect(row.conflictLevel).toBe('NONE')
    expect(row.conflictMessage).toBe('无冲突')
    scope.stop()
  })

  it('reports all-platform failures as errors and blocks unverified conflict results', async () => {
    const { batch, scope } = setup()
    vi.mocked(workflowApi.recommendBatch).mockResolvedValueOnce({
      ...response(),
      successCount: 0,
      failureCount: 2,
      items: [
        { platform: 'WEIBO', success: false, message: '没有账号样本' },
        { platform: 'XIAOHONGSHU', success: false, message: '没有版本' },
      ],
    })
    await batch.calculateBatch()
    expect(ElMessage.success).not.toHaveBeenCalled()
    expect(ElMessage.error).toHaveBeenCalled()
    expect(batch.canSchedule.value).toBe(false)
    vi.mocked(workflowApi.scheduleConflictCheck).mockRejectedValue(new Error('offline'))
    await batch.calculateBatch()
    expect(batch.planRows.value[0].conflictMessage).toBe('冲突检测失败')
    expect(batch.canSchedule.value).toBe(false)
    scope.stop()
  })

  it('retries a lost batch response with the same normalized payload key after row reordering', async () => {
    const { batch, scope } = setup()
    await batch.calculateBatch()
    vi.mocked(workflowApi.createSchedulesBatch).mockRejectedValueOnce(new Error('response lost'))
    await batch.createBatchSchedules()
    batch.planRows.value.reverse()
    for (const row of batch.planRows.value) {
      row.selectedAt = '2030-01-01T02:00:00Z'
      row.recommendedAt = '2030-01-01T02:00:00Z'
    }
    await batch.createBatchSchedules()
    const calls = vi.mocked(workflowApi.createSchedulesBatch).mock.calls
    expect(calls[1][0]).toEqual(calls[0][0])
    expect(calls[0][0].items.map((item) => item.account_id)).toEqual([11, 22])
    expect(calls[0][0].items[0].scheduled_at).toBe('2030-01-01T02:00:00.000Z')
    scope.stop()
  })

  it('does not reuse the old batch key after edits and remembers a retry of the original intent', async () => {
    const { batch, scope } = setup()
    await batch.calculateBatch()
    vi.mocked(workflowApi.createSchedulesBatch).mockRejectedValueOnce(new Error('response lost'))
    await batch.createBatchSchedules()
    const row = batch.planRows.value[0]
    const originalTime = row.selectedAt
    row.selectedAt = '2030-01-01T11:00:00+08:00'
    row.accountId = 33
    await batch.createBatchSchedules()
    row.selectedAt = originalTime
    row.accountId = 11
    await batch.createBatchSchedules()
    const calls = vi.mocked(workflowApi.createSchedulesBatch).mock.calls
    expect(calls[1][0].idempotency_key).not.toBe(calls[0][0].idempotency_key)
    expect(calls[2][0].idempotency_key).toBe(calls[0][0].idempotency_key)
    scope.stop()
  })
})
