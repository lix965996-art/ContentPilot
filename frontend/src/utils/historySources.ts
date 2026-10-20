export interface HistorySourceOption {
  value: string
  label: string
}

// Used only while fields metadata is loading or its request is unavailable.
export const fallbackHistorySources: HistorySourceOption[] = [
  { value: 'ACCOUNT_HISTORY', label: '账号历史数据（用户导入）' },
  { value: 'PUBLIC_BASELINE', label: '公开数据基线' },
  { value: 'YOUTUBE_PUBLIC_SAMPLE', label: 'YouTube 公开样本（非国内平台数据）' },
  { value: 'RESEARCH_DATASET', label: '公开研究数据集' },
  { value: 'SIMULATED', label: '演示模拟数据（不参与真实推荐）' },
]

export function historyInputSources(options: HistorySourceOption[]): HistorySourceOption[] {
  const inputs = options.filter((item) => item.value !== 'MIXED')
  return inputs.length ? inputs : [...fallbackHistorySources]
}
