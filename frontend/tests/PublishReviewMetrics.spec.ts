import { describe, expect, it } from 'vitest'
import { evaluatePublishReviewRecord, groupStats } from '@/utils/publishReviewMetrics'

const input = {
  scheduleId: 1,
  title: '内容',
  platformKey: 'WEIBO',
  platformLabel: '微博',
  dataSource: 'MANUAL',
  timeSource: 'RECOMMENDED',
  impressions: 100,
  followers: 1000,
  likes: 10,
}

describe('publish review metric basis', () => {
  it('uses the persisted denominator instead of silently switching to impressions', () => {
    const followerRecord = evaluatePublishReviewRecord({ ...input, metricBasis: 'FOLLOWERS' })
    const impressionRecord = evaluatePublishReviewRecord({ ...input, metricBasis: 'IMPRESSIONS' })
    expect(followerRecord.engagementRate).toBe(1)
    expect(followerRecord.rateDenominator).toBe(1000)
    expect(impressionRecord.engagementRate).toBe(10)
    expect(impressionRecord.rateDenominator).toBe(100)
  })

  it('keeps an explicit unavailable API rate unavailable even when counts are present', () => {
    const record = evaluatePublishReviewRecord({
      ...input,
      metricBasis: 'IMPRESSIONS',
      apiEngagementRate: null,
      rateAvailable: false,
    })
    expect(record.engagementRate).toBeNull()
    expect(record.isRealValid).toBe(false)
    expect(record.rateStatusLabel).toBe('不可计算')
  })

  it('does not guess a denominator for legacy unknown or mixed records', () => {
    for (const metricBasis of ['UNKNOWN', 'MIXED', 'invalid']) {
      const record = evaluatePublishReviewRecord({ ...input, metricBasis, apiEngagementRate: 10 })
      expect(record.engagementRate).toBeNull()
      expect(record.rateAvailable).toBe(false)
      expect(record.isRealValid).toBe(false)
    }
  })

  it('does not average rates calculated with different denominators', () => {
    const records = ['FOLLOWERS', 'IMPRESSIONS'].map((metricBasis) =>
      evaluatePublishReviewRecord({ ...input, metricBasis }),
    )
    expect(groupStats(records)).toMatchObject({
      metricBasis: 'MIXED',
      validCount: 2,
      avg: null,
      rateAvailable: false,
    })
  })

  it('includes simulated rates only when the caller explicitly requests the demonstration scope', () => {
    const record = evaluatePublishReviewRecord({
      ...input,
      dataSource: 'SIMULATED',
      metricBasis: 'IMPRESSIONS',
    })
    expect(record.isRealValid).toBe(false)
    expect(groupStats([record]).avg).toBeNull()
    expect(groupStats([record], { includeSimulated: true })).toMatchObject({
      avg: 10,
      sourceScope: 'SIMULATED',
      rateAvailable: true,
    })
  })

  it('never combines demonstration and real samples into an effect result', () => {
    const records = ['MANUAL', 'SIMULATED'].map((dataSource) =>
      evaluatePublishReviewRecord({ ...input, dataSource, metricBasis: 'IMPRESSIONS' }),
    )
    expect(groupStats(records, { includeSimulated: true })).toMatchObject({
      sourceScope: 'MIXED',
      avg: null,
      rateAvailable: false,
    })
  })

  it('does not treat missing data provenance as real platform feedback', () => {
    const record = evaluatePublishReviewRecord({
      ...input,
      dataSource: undefined,
      metricBasis: 'IMPRESSIONS',
    })
    expect(record.dataSource).toBe('UNKNOWN')
    expect(record.participatesInRealEffect).toBe(false)
    expect(groupStats([record]).avg).toBeNull()
  })
})
