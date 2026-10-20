import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ScheduleAdvisor from '@/components/ScheduleAdvisor.vue'
import { workflowApi } from '@/api/workflow'
import type { PlatformAccount, PublishTimeRecommendation, Schedule } from '@/types/business'

vi.mock('@/api/workflow', () => ({
  workflowApi: { recommend: vi.fn(), scheduleConflictCheck: vi.fn(), createSchedule: vi.fn() },
}))
vi.mock('element-plus', async (original) => ({
  ...(await original<typeof import('element-plus')>()),
  ElMessage: { warning: vi.fn(), error: vi.fn(), success: vi.fn() },
}))

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((yes) => {
    resolve = yes
  })
  return { promise, resolve }
}

function recommendation(variantId = 11): PublishTimeRecommendation {
  return {
    id: 100 + variantId,
    articleId: 1,
    variantId,
    platform: 'WEIBO',
    recommendedAt: '2030-01-01T10:00:00+08:00',
    contentType: 'KNOWLEDGE',
    contentTypeName: '知识科普',
    conflicts: [],
    alternatives: [],
    warnings: [],
    reasons: [],
    dataSource: { baseline: '公开基线', accountHistory: '账号历史', sourceTypes: [] },
    dataSufficiency: { message: '样本充足' },
  } as unknown as PublishTimeRecommendation
}

const props = {
  articleId: 1,
  variantId: 11,
  platform: 'WEIBO' as const,
  accounts: [
    { id: 21, platform: 'WEIBO', accountName: '测试账号', status: 'CONNECTED' },
  ] as PlatformAccount[],
  reviewStatus: 'APPROVED',
}

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(workflowApi.recommend).mockImplementation(async (request) =>
    recommendation(request.variant_id),
  )
  vi.mocked(workflowApi.scheduleConflictCheck).mockResolvedValue({
    platform: 'WEIBO',
    scheduledAt: '2030-01-01T10:00:00+08:00',
    hasConflict: false,
    hasDensityWarning: false,
    conflicts: [],
  })
  vi.mocked(workflowApi.createSchedule).mockResolvedValue({ id: 99 } as Schedule)
})

describe('schedule advisor requests and schedule intent', () => {
  it('resets loading on a version change and an old finally cannot stop a new request', async () => {
    const old = deferred<PublishTimeRecommendation>()
    const fresh = deferred<PublishTimeRecommendation>()
    vi.mocked(workflowApi.recommend)
      .mockReturnValueOnce(old.promise)
      .mockReturnValueOnce(fresh.promise)
    const { rerender } = render(ScheduleAdvisor, { props, global: { plugins: [ElementPlus] } })
    const calculate = screen.getByTestId('advisor-calculate') as HTMLButtonElement
    await fireEvent.click(calculate)
    expect(calculate.disabled).toBe(true)

    await rerender({ ...props, variantId: 12 })
    expect(calculate.disabled).toBe(false)
    await fireEvent.click(calculate)
    old.resolve(recommendation(11))
    await Promise.resolve()
    await Promise.resolve()
    expect(calculate.disabled).toBe(true)
    expect(screen.queryByTestId('advisor-schedule')).toBeNull()

    fresh.resolve(recommendation(12))
    await screen.findByTestId('advisor-schedule')
    await waitFor(() => expect(calculate.disabled).toBe(false))
    expect(vi.mocked(workflowApi.recommend).mock.calls[1][0].variant_id).toBe(12)
  })

  it('clears a pending article recommendation without waiting for the old request', async () => {
    const pending = deferred<PublishTimeRecommendation>()
    vi.mocked(workflowApi.recommend).mockReturnValueOnce(pending.promise)
    const { rerender } = render(ScheduleAdvisor, { props, global: { plugins: [ElementPlus] } })
    await fireEvent.click(screen.getByTestId('advisor-calculate'))
    await rerender({ ...props, articleId: 2, variantId: 22 })
    expect((screen.getByTestId('advisor-calculate') as HTMLButtonElement).disabled).toBe(false)
    pending.resolve(recommendation())
    await Promise.resolve()
    expect(screen.queryByTestId('advisor-schedule')).toBeNull()
  })

  it('keeps the key after a lost response and binds edited variants to a new key', async () => {
    vi.mocked(workflowApi.createSchedule).mockRejectedValueOnce(new Error('response lost'))
    const { rerender } = render(ScheduleAdvisor, { props, global: { plugins: [ElementPlus] } })
    await fireEvent.click(screen.getByTestId('advisor-calculate'))
    await fireEvent.click(await screen.findByTestId('advisor-schedule'))
    await waitFor(() =>
      expect((screen.getByTestId('advisor-schedule') as HTMLButtonElement).disabled).toBe(false),
    )
    await fireEvent.click(screen.getByTestId('advisor-schedule'))
    await waitFor(() => expect(workflowApi.createSchedule).toHaveBeenCalledTimes(2))
    const original = vi.mocked(workflowApi.createSchedule).mock.calls[0][0]
    expect(original.scheduled_at).toBe('2030-01-01T02:00:00.000Z')
    expect(vi.mocked(workflowApi.createSchedule).mock.calls[1][0].idempotency_key).toBe(
      original.idempotency_key,
    )

    await rerender({ ...props, variantId: 12 })
    await fireEvent.click(screen.getByTestId('advisor-calculate'))
    await fireEvent.click(await screen.findByTestId('advisor-schedule'))
    await waitFor(() => expect(workflowApi.createSchedule).toHaveBeenCalledTimes(3))
    expect(vi.mocked(workflowApi.createSchedule).mock.calls[2][0].idempotency_key).not.toBe(
      original.idempotency_key,
    )

    await rerender(props)
    await fireEvent.click(screen.getByTestId('advisor-calculate'))
    await fireEvent.click(await screen.findByTestId('advisor-schedule'))
    await waitFor(() => expect(workflowApi.createSchedule).toHaveBeenCalledTimes(4))
    expect(vi.mocked(workflowApi.createSchedule).mock.calls[3][0].idempotency_key).toBe(
      original.idempotency_key,
    )
  })
})
