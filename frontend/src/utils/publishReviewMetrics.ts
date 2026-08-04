export type RateStatus = 'ok' | 'uncalculable' | 'anomaly'

export type FieldStatus = 'ok' | 'missing' | 'anomaly'

export interface PublishReviewRecord {
  scheduleId: number
  title: string
  platformKey: string
  platformLabel: string
  dataSource: string
  dataSourceLabel: string
  participatesInRealEffect: boolean
  timeSource: string
  timeSourceLabel: string
  isRecommendedGroup: boolean
  scheduledAt: string | null
  recommendedAt: string | null
  actualPublishAt: string | null
  deviationMinutes: number | null
  impressions: number | null
  likes: number | null
  comments: number | null
  collects: number | null
  shares: number | null
  followers: number | null
  engagementTotal: number | null
  apiEngagementRate: number | null
  engagementRate: number | null
  rateStatus: RateStatus
  rateStatusLabel: string
  anomalyReason: string | null
  isRealValid: boolean
  completeness: number
  fieldStatus: {
    impressions: FieldStatus
    likes: FieldStatus
    comments: FieldStatus
    collects: FieldStatus
    shares: FieldStatus
    followers: FieldStatus
    rate: FieldStatus
  }
}

export const DATA_SOURCE_META: Record<
  string,
  { label: string; participates: boolean; purpose: string }
> = {
  SIMULATED: {
    label: '演示数据 SIMULATED',
    participates: false,
    purpose: '页面与流程演示，不参与真实效果结论',
  },
  IMPORTED: {
    label: '用户导入',
    participates: true,
    purpose: '批量导入复盘，参与真实效果计算',
  },
  MANUAL: {
    label: '手工录入',
    participates: true,
    purpose: '运营手工录入，参与真实效果计算',
  },
  PLATFORM: {
    label: '真实平台回传',
    participates: true,
    purpose: '平台 API 回传，参与真实效果计算',
  },
  REAL: {
    label: '真实平台回传',
    participates: true,
    purpose: '平台 API 回传，参与真实效果计算',
  },
}

export const TIME_SOURCE_LABEL: Record<string, string> = {
  RECOMMENDED: '系统推荐',
  ALTERNATIVE: '备选推荐',
  CUSTOM: '自选时间',
}

const MAX_VALID_RATE = 100

function normalizeSource(source: string | undefined) {
  const key = String(source || 'MANUAL').toUpperCase()
  return DATA_SOURCE_META[key] ? key : 'MANUAL'
}

function sourceMeta(source: string | undefined) {
  const key = normalizeSource(source)
  return { key, ...(DATA_SOURCE_META[key] || DATA_SOURCE_META.MANUAL) }
}

function hasKnownInteraction(record: {
  likes: number | null
  comments: number | null
  collects: number | null
  shares: number | null
}) {
  return [record.likes, record.comments, record.collects, record.shares].some(
    (value) => value !== null && value !== undefined,
  )
}

function interactionSum(record: {
  likes: number | null
  comments: number | null
  collects: number | null
  shares: number | null
}) {
  return (record.likes ?? 0) + (record.comments ?? 0) + (record.collects ?? 0) + (record.shares ?? 0)
}

function fieldStatus(value: number | null | undefined, anomaly = false): FieldStatus {
  if (anomaly) return 'anomaly'
  if (value === null || value === undefined) return 'missing'
  return 'ok'
}

export function evaluatePublishReviewRecord(input: {
  scheduleId: number
  title: string
  platformKey: string
  platformLabel: string
  dataSource?: string
  timeSource: string
  scheduledAt?: string | null
  recommendedAt?: string | null
  actualPublishAt?: string | null
  deviationMinutes?: number | null
  impressions?: number | null
  likes?: number | null
  comments?: number | null
  collects?: number | null
  shares?: number | null
  followers?: number | null
  engagementTotal?: number | null
  apiEngagementRate?: number | null
}): PublishReviewRecord {
  const source = sourceMeta(input.dataSource)
  const impressions = input.impressions ?? null
  const likes = input.likes ?? null
  const comments = input.comments ?? null
  const collects = input.collects ?? null
  const shares = input.shares ?? null
  const followers = input.followers ?? null
  const apiEngagementRate = input.apiEngagementRate ?? null
  const hasBreakdown = hasKnownInteraction({ likes, comments, collects, shares })

  let rateStatus: RateStatus = 'uncalculable'
  let engagementRate: number | null = null
  let anomalyReason: string | null = null

  if (apiEngagementRate !== null && (apiEngagementRate > MAX_VALID_RATE || apiEngagementRate < 0)) {
    rateStatus = 'anomaly'
    anomalyReason = `后端互动率 ${apiEngagementRate}% 超出合理范围`
  } else if (!hasBreakdown) {
    rateStatus = 'uncalculable'
    anomalyReason = '点赞/评论/收藏/转发均未录入，无法计算互动率'
  } else if (!impressions || impressions <= 0) {
    rateStatus = 'uncalculable'
    anomalyReason = '缺少有效浏览量/曝光量'
  } else {
    const total = interactionSum({ likes, comments, collects, shares })
    const computed = Number(((total / impressions) * 100).toFixed(2))
    if (computed > MAX_VALID_RATE || computed < 0 || total > impressions) {
      rateStatus = 'anomaly'
      anomalyReason = '互动量与曝光量不匹配'
    } else {
      rateStatus = 'ok'
      engagementRate = computed
    }
  }

  const filledFields = [
    impressions !== null && impressions > 0,
    likes !== null,
    comments !== null,
    collects !== null,
    shares !== null,
    followers !== null,
  ].filter(Boolean).length
  const completeness = Math.round((filledFields / 6) * 100)

  const isRecommendedGroup = input.timeSource === 'RECOMMENDED' || input.timeSource === 'ALTERNATIVE'
  const isRealValid =
    source.key !== 'SIMULATED' && source.participates && rateStatus === 'ok' && !anomalyReason

  const rateFieldStatus: FieldStatus =
    rateStatus === 'ok' ? 'ok' : rateStatus === 'anomaly' ? 'anomaly' : 'missing'

  return {
    scheduleId: input.scheduleId,
    title: input.title,
    platformKey: input.platformKey,
    platformLabel: input.platformLabel,
    dataSource: source.key,
    dataSourceLabel: source.label,
    participatesInRealEffect: source.participates && source.key !== 'SIMULATED',
    timeSource: input.timeSource,
    timeSourceLabel: TIME_SOURCE_LABEL[input.timeSource] || input.timeSource,
    isRecommendedGroup,
    scheduledAt: input.scheduledAt ?? null,
    recommendedAt: input.recommendedAt ?? null,
    actualPublishAt: input.actualPublishAt ?? null,
    deviationMinutes: input.deviationMinutes ?? null,
    impressions,
    likes,
    comments,
    collects,
    shares,
    followers,
    engagementTotal: input.engagementTotal ?? null,
    apiEngagementRate,
    engagementRate,
    rateStatus,
    rateStatusLabel:
      rateStatus === 'ok'
        ? `${engagementRate}%`
        : rateStatus === 'anomaly'
          ? '数据异常'
          : '不可计算',
    anomalyReason,
    isRealValid,
    completeness,
    fieldStatus: {
      impressions: fieldStatus(impressions, impressions !== null && impressions <= 0),
      likes: fieldStatus(likes),
      comments: fieldStatus(comments),
      collects: fieldStatus(collects),
      shares: fieldStatus(shares),
      followers: fieldStatus(followers),
      rate: rateFieldStatus,
    },
  }
}

export function median(values: number[]) {
  if (!values.length) return null
  const sorted = [...values].sort((left, right) => left - right)
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 ? sorted[mid] : Number(((sorted[mid - 1] + sorted[mid]) / 2).toFixed(2))
}

export function groupStats(records: PublishReviewRecord[]) {
  const validRates = records
    .filter((record) => record.isRealValid && record.engagementRate !== null)
    .map((record) => record.engagementRate as number)

  if (!validRates.length) {
    return {
      count: records.length,
      validCount: 0,
      avg: null,
      median: null,
      min: null,
      max: null,
      status: records.length ? '无有效样本' : '暂无数据',
    }
  }

  return {
    count: records.length,
    validCount: validRates.length,
    avg: Number((validRates.reduce((sum, value) => sum + value, 0) / validRates.length).toFixed(2)),
    median: median(validRates),
    min: Math.min(...validRates),
    max: Math.max(...validRates),
    status: validRates.length >= 3 ? '可比较' : '样本不足，仅展示描述性结果',
  }
}

export function formatDateTime(value: string | null | undefined) {
  if (!value) return '—'
  return value.slice(0, 16).replace('T', ' ')
}

export function formatDeviation(minutes: number | null | undefined) {
  if (minutes === null || minutes === undefined) return '—'
  if (minutes === 0) return '准时'
  const abs = Math.abs(minutes)
  const hours = Math.floor(abs / 60)
  const mins = abs % 60
  const text = hours ? `${hours}小时${mins}分` : `${mins}分钟`
  return minutes > 0 ? `延后 ${text}` : `提前 ${text}`
}
