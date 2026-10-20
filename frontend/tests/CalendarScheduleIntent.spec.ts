import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { nextTick } from 'vue'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CalendarPage from '@/pages/CalendarPage.vue'
import { workflowApi } from '@/api/workflow'
import type { Article, PlatformAccount, PublishTimeRecommendation, Variant } from '@/types/business'

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: { create: '1', article: '1', variant: '11' } }),
}))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ canManageBusiness: true }) }))
vi.mock('@fullcalendar/vue3', () => ({ default: { template: '<div />' } }))
vi.mock('@/api/workflow', () => ({
  workflowApi: {
    articles: vi.fn(),
    variants: vi.fn(),
    platformAccounts: vi.fn(),
    schedules: vi.fn(),
    scheduleBacklog: vi.fn(),
    recommend: vi.fn(),
    scheduleConflictCheck: vi.fn(),
    createSchedule: vi.fn(),
  },
}))
vi.mock('element-plus', async (original) => ({
  ...(await original<typeof import('element-plus')>()),
  ElMessage: { warning: vi.fn(), error: vi.fn(), success: vi.fn() },
}))

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(workflowApi.articles).mockResolvedValue({
    items: [
      { id: 1, title: '排期测试文章' },
      { id: 2, title: '另一篇文章' },
    ] as Article[],
    total: 2,
    page: 1,
    pageSize: 100,
  })
  vi.mocked(workflowApi.variants).mockResolvedValue([
    { id: 11, platform: 'WEIBO', versionNo: 1, reviewStatus: 'APPROVED', title: '测试版本' },
  ] as Variant[])
  vi.mocked(workflowApi.platformAccounts).mockResolvedValue([
    { id: 21, platform: 'WEIBO', accountName: '测试账号', status: 'CONNECTED' },
  ] as PlatformAccount[])
  vi.mocked(workflowApi.schedules).mockResolvedValue([])
  vi.mocked(workflowApi.scheduleBacklog).mockResolvedValue([])
  vi.mocked(workflowApi.recommend).mockResolvedValue({
    id: 101,
    recommendedAt: '2030-01-01T10:00:00+08:00',
    contentType: 'KNOWLEDGE',
    alternatives: [],
    reasons: [],
    warnings: [],
    dataSource: { baseline: '', accountHistory: '' },
    dataSufficiency: { message: '' },
  } as unknown as PublishTimeRecommendation)
  vi.mocked(workflowApi.scheduleConflictCheck).mockResolvedValue({
    platform: 'WEIBO',
    scheduledAt: '',
    hasConflict: false,
    hasDensityWarning: false,
    conflicts: [],
  })
  vi.mocked(workflowApi.createSchedule).mockRejectedValue(new Error('response lost'))
})

describe('calendar schedule intent after an uncertain response', () => {
  it('retries the original time with the original key and uses a new key for an edited time', async () => {
    render(CalendarPage, {
      global: {
        plugins: [ElementPlus],
        stubs: {
          ElDatePicker: {
            props: ['modelValue'],
            emits: ['update:modelValue', 'change'],
            template:
              '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" @change="$emit(\'change\')" />',
          },
        },
      },
    })
    const submit = await screen.findByTestId('schedule-create-submit')
    const input = (await screen.findByTestId('schedule-create-time')) as HTMLInputElement
    await waitFor(() => expect(input.value).toBe('2030-01-01T10:00'))
    for (const at of ['2030-01-01T10:00', '2030-01-01T10:00', '2030-01-01T11:00']) {
      await fireEvent.update(input, at)
      await fireEvent.change(input)
      await fireEvent.click(submit)
      await waitFor(() => expect((submit as HTMLButtonElement).disabled).toBe(false))
    }
    const calls = vi.mocked(workflowApi.createSchedule).mock.calls
    expect(calls).toHaveLength(3)
    expect(calls[0][0].scheduled_at).toBe('2030-01-01T02:00:00.000Z')
    expect(calls[1][0].idempotency_key).toBe(calls[0][0].idempotency_key)
    expect(calls[2][0].idempotency_key).not.toBe(calls[0][0].idempotency_key)
  })
})

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}

function renderSelectionCalendar() {
  return render(CalendarPage, {
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

describe('calendar article version loading', () => {
  it('keeps the latest article versions when earlier responses arrive late', async () => {
    renderSelectionCalendar()
    const submit = (await screen.findByTestId('schedule-create-submit')) as HTMLButtonElement
    await waitFor(() => expect(submit.disabled).toBe(false))
    const old = deferred<Variant[]>()
    const fresh = deferred<Variant[]>()
    vi.mocked(workflowApi.variants)
      .mockReturnValueOnce(old.promise)
      .mockReturnValueOnce(fresh.promise)
    const article = screen.getByTestId('schedule-create-article')
    const variant = screen.getByTestId('schedule-create-variant') as HTMLSelectElement
    await fireEvent.update(article, '2')
    await fireEvent.update(article, '1')
    expect(variant.disabled).toBe(true)
    expect(submit.disabled).toBe(true)
    await fireEvent.click(submit)
    expect(workflowApi.createSchedule).not.toHaveBeenCalled()

    fresh.resolve([{ id: 11, platform: 'WEIBO', reviewStatus: 'APPROVED' }] as Variant[])
    await waitFor(() => expect(variant.value).toBe('11'))
    expect(submit.disabled).toBe(false)
    old.resolve([{ id: 22, platform: 'XIAOHONGSHU', reviewStatus: 'APPROVED' }] as Variant[])
    await old.promise
    await nextTick()
    expect(variant.value).toBe('11')
    expect(variant.options).toHaveLength(1)
    expect(workflowApi.recommend).toHaveBeenLastCalledWith(
      expect.objectContaining({ article_id: 1, variant_id: 11, platform: 'WEIBO' }),
    )
    await fireEvent.click(submit)
    await waitFor(() => expect(workflowApi.createSchedule).toHaveBeenCalledOnce())
    expect(workflowApi.createSchedule).toHaveBeenCalledWith(
      expect.objectContaining({ article_id: 1, variant_id: 11, platform: 'WEIBO' }),
    )
  })

  it('clears the old version on failure and recovers after selecting another article', async () => {
    renderSelectionCalendar()
    const submit = (await screen.findByTestId('schedule-create-submit')) as HTMLButtonElement
    await waitFor(() => expect(submit.disabled).toBe(false))
    const failure = deferred<Variant[]>()
    vi.mocked(workflowApi.variants).mockReturnValueOnce(failure.promise)
    const article = screen.getByTestId('schedule-create-article')
    const variant = screen.getByTestId('schedule-create-variant') as HTMLSelectElement
    await fireEvent.update(article, '2')
    failure.reject(new Error('connection interrupted'))
    await waitFor(() => expect(variant.disabled).toBe(false))
    expect(variant.options).toHaveLength(0)
    expect(submit.disabled).toBe(true)
    await fireEvent.click(submit)
    expect(workflowApi.createSchedule).not.toHaveBeenCalled()

    await fireEvent.update(article, '1')
    await waitFor(() => expect(variant.value).toBe('11'))
    expect(submit.disabled).toBe(false)
    await fireEvent.click(submit)
    await waitFor(() => expect(workflowApi.createSchedule).toHaveBeenCalledOnce())
  })
})
