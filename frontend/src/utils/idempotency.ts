/** Generate a stable idempotency key for a create attempt. */
export function newIdempotencyKey(prefix = 'schedule'): string {
  const cryptoObject = globalThis.crypto
  if (cryptoObject && typeof cryptoObject.randomUUID === 'function') {
    return `${prefix}-${cryptoObject.randomUUID()}`
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`
}

/** UI date pickers use the project's Asia/Shanghai business-wall time. */
export function normalizeScheduleTime(value: string): string {
  const input = value.trim().replace(' ', 'T')
  const zoned = /(?:Z|[+-]\d{2}:\d{2})$/i.test(input) ? input : `${input}+08:00`
  const date = new Date(zoned)
  return Number.isFinite(date.getTime()) ? date.toISOString() : value
}

export function normalizeSchedulePayload<
  T extends { scheduled_at: string; recommended_at?: string },
>(payload: T): T {
  return {
    ...payload,
    scheduled_at: normalizeScheduleTime(payload.scheduled_at),
    ...(payload.recommended_at
      ? { recommended_at: normalizeScheduleTime(payload.recommended_at) }
      : {}),
  }
}

function stableValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stableValue)
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value)
        .filter(([, item]) => item !== undefined)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([key, item]) => [key, stableValue(item)]),
    )
  }
  return value
}

/** Keep retries tied to the submitted payload, including after a lost response. */
export function createIdempotencyIntent(prefix = 'schedule') {
  const keys = new Map<string, string>()
  return {
    keyFor(payload: unknown): string {
      const fingerprint = JSON.stringify(stableValue(payload))
      const existing = keys.get(fingerprint)
      if (existing) return existing
      const key = newIdempotencyKey(prefix)
      keys.set(fingerprint, key)
      // A long-lived page should not retain every historical editing attempt.
      if (keys.size > 256) keys.delete(keys.keys().next().value!)
      return key
    },
  }
}
