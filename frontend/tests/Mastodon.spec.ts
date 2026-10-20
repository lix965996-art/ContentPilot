import { describe, expect, it } from 'vitest'
import { buildMastodonText, mastodonLimits, mastodonTextLength } from '@/utils/mastodon'
import { canUseMastodonApi, publishModeOptions } from '@/composables/usePublishModes'
import type { PlatformAccount } from '@/types/business'

const account = {
  platform: 'MASTODON',
  status: 'CONNECTED',
  availablePublishModes: ['REAL_API'],
  publicPublishEnabled: true,
} as PlatformAccount

describe('Mastodon publishing preparation', () => {
  it('counts full emoji as one character and normalizes links using the server limit', () => {
    expect(mastodonTextLength('👨‍👩‍👧‍👦🇨🇳e\u0301')).toBe(3)
    expect(mastodonTextLength('看看 https://example.com/a/very/long/path。')).toBe(27)
    expect(mastodonTextLength('https://example.com/a', 12)).toBe(12)
    expect(mastodonTextLength('https://example.com/a https://example.net/b')).toBe(47)
  })

  it('includes the title, topics, and separators in the total post length', () => {
    const post = buildMastodonText(' 标题 ', '正文', ['#AI', 'A I', '技术'])
    expect(post).toBe('标题\n\n正文\n\n#AI #技术')
    expect(mastodonTextLength(post)).toBe(15)
  })

  it('uses conservative defaults and honors stricter server limits', () => {
    expect(mastodonLimits()).toEqual({
      maxCharacters: 500,
      charactersReservedPerUrl: 23,
      maxMediaAttachments: 4,
    })
    expect(mastodonLimits({ maxCharacters: 300, maxMediaAttachments: 2 })).toMatchObject({
      maxCharacters: 300,
      maxMediaAttachments: 2,
    })
    expect(mastodonLimits({ maxMediaAttachments: 8 }).maxMediaAttachments).toBe(4)
  })

  it('requires a verified connection and an enabled real publishing switch', () => {
    expect(canUseMastodonApi(account)).toBe(true)
    for (const patch of [
      { publicPublishEnabled: false },
      { status: 'INVALID' as const },
      { availablePublishModes: [] },
      { platform: 'BLUESKY' as const },
    ]) {
      expect(canUseMastodonApi({ ...account, ...patch })).toBe(false)
    }
    expect(publishModeOptions('MASTODON', account)[0]?.disabled).toBe(false)
    expect(publishModeOptions('MASTODON', { ...account, status: 'CONNECTING' })[0]?.disabled).toBe(
      true,
    )
  })
})
