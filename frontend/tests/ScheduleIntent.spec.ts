import { describe, expect, it } from 'vitest'
import { createIdempotencyIntent, normalizeSchedulePayload } from '@/utils/idempotency'

describe('schedule intent identity', () => {
  const payload = {
    article_id: 1,
    variant_id: 2,
    platform: 'WEIBO',
    account_id: 3,
    scheduled_at: '2030-01-01T10:00:00',
    recommended_at: '2030-01-01T10:00:00+08:00',
    time_source: 'RECOMMENDED',
    publish_mode: 'REAL_API',
  }

  it('identifies timezone-equivalent requests independently of object property order', () => {
    const intent = createIdempotencyIntent()
    const first = normalizeSchedulePayload(payload)
    const second = normalizeSchedulePayload({
      ...payload,
      scheduled_at: '2030-01-01T02:00:00Z',
      recommended_at: '2030-01-01 10:00:00',
    })
    expect(first).toEqual(second)
    expect(intent.keyFor(first)).toBe(
      intent.keyFor(Object.fromEntries(Object.entries(second).reverse())),
    )
  })

  it.each([
    { article_id: 5 },
    { variant_id: 5 },
    { account_id: 5 },
    { platform: 'MASTODON' },
    { scheduled_at: '2030-01-01T11:00:00+08:00' },
    { publish_mode: 'MANUAL_CONFIRM' },
    { time_source: 'CUSTOM' },
  ])('creates a new intent for an effective edit %j and retains the original retry', (edit) => {
    const intent = createIdempotencyIntent()
    const original = normalizeSchedulePayload(payload)
    const originalKey = intent.keyFor(original)
    expect(intent.keyFor(normalizeSchedulePayload({ ...payload, ...edit }))).not.toBe(originalKey)
    expect(intent.keyFor(original)).toBe(originalKey)
  })
})
