import { describe, expect, it } from 'vitest'
import { blueskyTextLength, buildBlueskyText } from '@/utils/bluesky'
import { canUseBlueskyApi, publishModeOptions } from '@/composables/usePublishModes'
import type { PlatformAccount } from '@/types/business'

const account = {
  platform: 'BLUESKY',
  status: 'CONNECTED',
  availablePublishModes: ['REAL_API'],
  publicPublishEnabled: true,
} as PlatformAccount

describe('Bluesky publishing preparation', () => {
  it('counts joined emoji and combining characters as single graphemes', () => {
    expect(blueskyTextLength('👨‍👩‍👧‍👦🇨🇳e\u0301')).toBe(3)
    expect(blueskyTextLength('你'.repeat(300))).toBe(300)
  })

  it('previews the full title, body and first four normalized unique hashtags', () => {
    expect(
      buildBlueskyText(' 标题 ', '正文', ['#AI', 'A I', '技术', '生活', '学习', '第五个']),
    ).toBe('标题\n\n正文\n\n#AI #技术 #生活 #学习')
    expect(buildBlueskyText('标题', '标题已经在正文里', [])).toBe('标题已经在正文里')
  })

  it('does not enable real publishing from a connected account alone', () => {
    expect(canUseBlueskyApi({ ...account, publicPublishEnabled: false })).toBe(false)
    expect(canUseBlueskyApi({ ...account, status: 'INVALID' })).toBe(false)
    expect(canUseBlueskyApi({ ...account, availablePublishModes: [] })).toBe(false)
    expect(canUseBlueskyApi({ ...account, platform: 'X' })).toBe(false)
    expect(
      publishModeOptions('BLUESKY', { ...account, publicPublishEnabled: false })[0]?.disabled,
    ).toBe(true)
    expect(publishModeOptions('BLUESKY', account)[0]?.disabled).toBe(false)
  })
})
