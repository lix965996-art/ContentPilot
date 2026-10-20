import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import RecommendationPage from '@/pages/RecommendationPage.vue'
import { workflowApi } from '@/api/workflow'
import type { ActivityAnalysis } from '@/types/business'

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ canManageBusiness: true }) }))
vi.mock('@/api/workflow', () => ({
  workflowApi: {
    articles: vi.fn(),
    platformAccounts: vi.fn(),
    activityContentTypes: vi.fn(),
    historyFields: vi.fn(),
    historyBatches: vi.fn(),
    activityAnalysis: vi.fn(),
  },
}))
vi.mock('@/components/ChartPanel.vue', () => ({ default: { template: '<div />' } }))

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(workflowApi.articles).mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    pageSize: 100,
  })
  vi.mocked(workflowApi.platformAccounts).mockResolvedValue([])
  vi.mocked(workflowApi.activityContentTypes).mockResolvedValue([])
  vi.mocked(workflowApi.historyBatches).mockResolvedValue({
    items: [],
    totalRecords: 0,
    bySource: [],
  })
  vi.mocked(workflowApi.activityAnalysis).mockResolvedValue({} as ActivityAnalysis)
})

async function openSourceOptions() {
  await fireEvent.click(screen.getByRole('tab', { name: '历史数据' }))
  await fireEvent.click(await screen.findByTestId('history-import-source'))
}

describe('history import source choices before the first upload', () => {
  it('loads authoritative input choices immediately and never offers aggregate MIXED', async () => {
    vi.mocked(workflowApi.historyFields).mockResolvedValue({
      fields: [],
      sourceTypes: [
        { value: 'ACCOUNT_HISTORY', label: '账号历史数据' },
        { value: 'RESEARCH_DATASET', label: '服务端公开研究数据集' },
        { value: 'MIXED', label: '混合来源（按记录查看）' },
      ],
    })
    render(RecommendationPage, { global: { plugins: [ElementPlus] } })
    await waitFor(() => expect(workflowApi.historyFields).toHaveBeenCalledOnce())
    await openSourceOptions()
    expect(await screen.findByRole('option', { name: '服务端公开研究数据集' })).toBeTruthy()
    expect(screen.queryByRole('option', { name: '混合来源（按记录查看）' })).toBeNull()
  })

  it('offers supported research and YouTube types when fields metadata is unavailable', async () => {
    vi.mocked(workflowApi.historyFields).mockRejectedValue(new Error('offline'))
    render(RecommendationPage, { global: { plugins: [ElementPlus] } })
    await openSourceOptions()
    expect(await screen.findByRole('option', { name: '公开研究数据集' })).toBeTruthy()
    expect(screen.getByRole('option', { name: 'YouTube 公开样本（非国内平台数据）' })).toBeTruthy()
    expect(screen.queryByRole('option', { name: '混合来源（按记录查看）' })).toBeNull()
    expect(screen.queryByRole('option', { name: /^公开数据集$/ })).toBeNull()
  })
})
