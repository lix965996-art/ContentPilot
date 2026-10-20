import { render, screen } from '@testing-library/vue'
import { describe, expect, it, vi } from 'vitest'
import PublishReviewPanel from '@/components/PublishReviewPanel.vue'
import type { DataScope } from '@/types/business'

vi.mock('@/api/workflow', () => ({ workflowApi: { publishDecision: vi.fn() } }))
vi.mock('@/components/ChartPanel.vue', () => ({
  default: {
    props: ['option'],
    template: '<div data-testid="chart">{{ JSON.stringify(option) }}</div>',
  },
}))

const row = {
  scheduleId: 1,
  title: '分母回归内容',
  platform: 'WEIBO',
  impressions: 100,
  followers: 1000,
  engagementTotal: 10,
  metricBasis: 'FOLLOWERS',
  dataSource: 'MANUAL',
  engagementRate: 1,
  rateAvailable: true,
  rateDenominator: 1000,
}

function renderReview(ranking: Array<Record<string, unknown>>, dataScope: DataScope = 'REAL') {
  return render(PublishReviewPanel, { props: { overview: {}, ranking, dataScope } })
}

describe('publish review panel', () => {
  it('renders the saved follower basis and a scatter chart without crashing', () => {
    renderReview([row])
    expect(screen.getByText('分母回归内容')).toBeTruthy()
    expect(screen.getByText('效果分布')).toBeTruthy()
    expect(screen.getAllByText('1%', { exact: false })).toHaveLength(3)
    expect(screen.getAllByTestId('chart')).toHaveLength(4)
  })

  it('shows an unavailable API rate instead of recomputing a percentage', () => {
    renderReview([{ ...row, engagementRate: null, rateAvailable: false, metricBasis: 'UNKNOWN' }])
    expect(screen.getByText('不可计算', { exact: false })).toBeTruthy()
    expect(screen.queryByText('效果分布')).toBeNull()
  })

  it('does not plot or aggregate mixed rate denominators', () => {
    renderReview([
      row,
      { ...row, scheduleId: 2, title: '曝光内容', metricBasis: 'IMPRESSIONS', engagementRate: 10 },
    ])
    expect(screen.queryByText('效果分布')).toBeNull()
    expect(screen.getByText('分组包含混合分母，无法合并互动率或计算提升。')).toBeTruthy()
  })

  it('labels demonstration comparisons and keeps them out of the real scope', async () => {
    const { rerender } = renderReview([{ ...row, dataSource: 'SIMULATED' }])
    expect(screen.queryByText('效果分布')).toBeNull()
    await rerender({
      overview: {},
      ranking: [{ ...row, dataSource: 'SIMULATED' }],
      dataScope: 'SIMULATED',
    })
    expect(screen.getByText('效果分布')).toBeTruthy()
    expect(screen.getByText('仅查看演示数据')).toBeTruthy()
    expect(
      screen.getByText('模拟互动数据，用于演示流程，不代表真实平台效果。', { exact: false }),
    ).toBeTruthy()
  })
})
