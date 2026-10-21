import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import EngagementLearningPanel from '@/components/EngagementLearningPanel.vue'
import { learningApi } from '@/api/learning'
import type { LearningStatus } from '@/types/learning'

const permissions = vi.hoisted(() => ({ canManageBusiness: true, canManageSystem: true }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => permissions }))
vi.mock('@/api/learning', () => ({
  learningApi: { status: vi.fn(), collect: vi.fn(), activate: vi.fn() },
}))

function status(): LearningStatus {
  return {
    readiness: { accepted: 0, accounts: 0, status: 'NEEDS_MATURE_OBSERVATIONS', reasons: {} },
    activeModels: { BLUESKY: null, MASTODON: null },
    models: [],
    exposureAvailable: false,
    items: [
      {
        scheduleId: 42,
        platform: 'BLUESKY',
        observedAt: '2026-10-20T00:00:00Z',
        ageSeconds: 86405,
        status: 'SUCCEEDED',
        errorCode: null,
        likes: 0,
        replies: null,
        reposts: 3,
        tasks: [],
      },
    ],
  }
}
function mount(manageModels = false) {
  return render(EngagementLearningPanel, {
    props: { showModelManagement: manageModels },
    global: { plugins: [ElementPlus] },
  })
}
beforeEach(() => {
  vi.resetAllMocks()
  permissions.canManageBusiness = true
  permissions.canManageSystem = true
  vi.mocked(learningApi.status).mockResolvedValue(status())
  vi.mocked(learningApi.collect).mockResolvedValue({ taskId: 'test-task', status: 'PENDING' })
})

describe('engagement learning', () => {
  it('keeps missing counters distinct from zero and explains the sampling window in management', async () => {
    mount(true)
    expect(await screen.findByText(/点赞 0 · 回复 未知 · 转发 3/)).toBeTruthy()
    expect(screen.getByText(/24小时15分钟/)).toBeTruthy()
    expect(screen.getByText(/曝光量不可用/)).toBeTruthy()
  })

  it('shows a retry after failure and clears the error on success', async () => {
    vi.mocked(learningApi.status).mockRejectedValueOnce(new Error('offline'))
    mount()
    expect(await screen.findByRole('alert')).toBeTruthy()
    await fireEvent.click(screen.getByText('刷新互动数据'))
    expect(await screen.findByText(/点赞 0/)).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('submits read-only collection once and waits for the durable background task', async () => {
    mount()
    const button = await screen.findByText('采集最新互动')
    await fireEvent.click(button)
    expect(await screen.findByRole('status')).toBeTruthy()
    expect(learningApi.collect).toHaveBeenCalledTimes(1)
    expect(learningApi.collect).toHaveBeenCalledWith(42, expect.any(String))
    expect(learningApi.activate).not.toHaveBeenCalled()
  })

  it('does not offer collection to read-only users', async () => {
    permissions.canManageBusiness = false
    mount()
    await screen.findByText(/点赞 0/)
    expect(screen.queryByText('采集最新互动')).toBeNull()
  })

  it('displays public research separately and blocks cross-platform activation', async () => {
    const data = status()
    data.items = []
    data.models = [
      {
        modelId: 'youtube-test',
        platform: 'YOUTUBE',
        algorithm: 'lightgbm',
        target: 'log1p(view_duration_fraction)',
        eligibility: 'EXPERIMENT_ONLY',
        researchOnly: true,
        activationBlocked: 'PLATFORM_MISMATCH',
        test: { count: 224, maeLog: 0.077, maeOriginal: 0.117, spearman: 0.698 },
        improvement: { relativeImprovement: 0.339, difference95CI: [0.02, 0.04] },
        trainRows: 669,
        validationRows: 223,
        testRows: 224,
        timeValidity: 'RETROSPECTIVE',
      },
    ]
    vi.mocked(learningApi.status).mockResolvedValue(data)
    mount(true)
    expect(await screen.findByText(/预测观看时长比例/)).toBeTruthy()
    expect(screen.getByText(/不能用于 Bluesky/)).toBeTruthy()
    expect(screen.getByText(/33.9%/)).toBeTruthy()
    expect(screen.getByText('启用模型').closest('button')?.disabled).toBe(true)
  })

  it('shows pending and failed tasks with recovery controls', async () => {
    const data = status()
    data.items[0]!.errorCode = 'AUTH_REQUIRED'
    data.items[0]!.tasks = [
      {
        id: 't',
        status: 'FAILED',
        dueAt: '2026-10-20T00:00:00Z',
        windowSeconds: 86400,
        errorCode: 'RATE_LIMITED',
      },
    ]
    vi.mocked(learningApi.status).mockResolvedValue(data)
    mount()
    expect(await screen.findByText('账号授权已失效，请重新连接')).toBeTruthy()
    expect(screen.queryByText(/AUTH_REQUIRED/)).toBeNull()
    expect(screen.getByText(/平台请求较多，请稍后重试/)).toBeTruthy()
    expect(screen.queryByText(/RATE_LIMITED/)).toBeNull()
    expect(screen.getByText('采集最新互动')).toBeTruthy()
  })

  it('keeps internal codes and model diagnostics out of the everyday view', async () => {
    const data = status()
    data.items[0]!.errorCode = 'INTERNAL_COLLECTION_DEBUG_CODE'
    data.readiness.reasons = { INTERNAL_READINESS_REASON: 1 }
    vi.mocked(learningApi.status).mockResolvedValue(data)
    mount()
    expect(await screen.findByText('采集暂未完成，请检查账号连接后重试')).toBeTruthy()
    expect(
      screen.queryByText(/INTERNAL_COLLECTION_DEBUG_CODE|INTERNAL_READINESS_REASON/),
    ).toBeNull()
    expect(screen.queryByText('模型与公开数据实验')).toBeNull()
    expect(screen.queryByText('24小时合格样本')).toBeNull()
    expect(screen.getByText('发布互动')).toBeTruthy()
  })

  it('does not show management details to non-admin users', async () => {
    permissions.canManageSystem = false
    mount(true)
    await screen.findByText(/点赞 0/)
    expect(screen.queryByText('24小时合格样本')).toBeNull()
    expect(screen.queryByText('模型与公开数据实验')).toBeNull()
  })

  it('ignores a stale response after the component is removed', async () => {
    let resolve!: (value: LearningStatus) => void
    vi.mocked(learningApi.status).mockReturnValue(
      new Promise((r) => {
        resolve = r
      }),
    )
    const view = mount()
    expect(await screen.findByText(/正在加载互动数据/)).toBeTruthy()
    view.unmount()
    resolve(status())
    await waitFor(() => expect(screen.queryByText(/点赞 0/)).toBeNull())
  })
})
