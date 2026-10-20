import { render, screen } from '@testing-library/vue'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PublishCenterPage from '@/pages/PublishCenterPage.vue'
import { workflowApi } from '@/api/workflow'
import type { Schedule } from '@/types/business'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ canManageSystem: true }),
}))
vi.mock('@/api/workflow', () => ({
  workflowApi: {
    schedules: vi.fn(),
  },
}))
vi.mock('element-plus', async (original) => ({
  ...(await original<typeof import('element-plus')>()),
  ElMessage: { warning: vi.fn(), error: vi.fn(), success: vi.fn() },
}))

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(workflowApi.schedules).mockResolvedValue([
    {
      id: 42,
      platform: 'WEIBO',
      articleTitle: '派发失败测试文章',
      scheduledAt: '2026-10-22T10:00:00',
      publishMode: 'REAL_API',
      status: 'FAILED',
      retryCount: 0,
      maxRetryCount: 3,
      errorMessage: '排期派发失败：scheduler unavailable；请重新排期',
    } as unknown as Schedule,
  ])
})

describe('publish center dispatch failure', () => {
  it('shows the dispatch failure reason and a reschedule entry', async () => {
    render(PublishCenterPage, { global: { plugins: [ElementPlus] } })

    expect(await screen.findByText(/排期派发失败/)).toBeTruthy()
    expect(screen.getByText('重新排期')).toBeTruthy()
  })
})
