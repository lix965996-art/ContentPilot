import { describe, expect, it } from 'vitest'

import { presentOperationError, redactTechnicalError } from '@/utils/operation-error'

describe('operation error presentation', () => {
  it('translates a WeChat 48001 response into an actionable user message', () => {
    const result = presentOperationError(
      '素材上传失败 [48001]: api unauthorized rid: 6a61f59f. 请配置默认封面素材 ID (default_cover_media_id); mode=DRAFT_ONLY; external_id=—',
      { type: 'PUBLISH', platform: 'WECHAT_OFFICIAL · ContentPilot 公众号' },
    )

    expect(result).toEqual({
      title: '公众号素材接口未授权',
      description:
        '公众号授权可能已失效，或当前账号没有素材上传权限。请先重新验证公众号连接，再检查封面素材。',
      primaryAction: 'platform-accounts',
      primaryActionLabel: '前往平台账号设置',
      secondaryAction: 'media',
      secondaryActionLabel: '检查封面素材',
      retryRecommended: false,
    })
  })

  it('recommends retrying temporary connection failures', () => {
    expect(
      presentOperationError('upstream request timeout', {
        type: 'PUBLISH',
        platform: 'X',
      }),
    ).toMatchObject({
      title: '平台连接暂时不可用',
      retryRecommended: true,
    })
  })

  it('routes AI provider authorization errors to administrator settings', () => {
    expect(
      presentOperationError('api unauthorized: invalid api key', {
        type: 'GENERATION',
        platform: 'WECHAT_OFFICIAL',
      }),
    ).toMatchObject({
      title: 'AI 模型服务授权异常',
      primaryAction: 'settings',
      retryRecommended: false,
    })
  })

  it('redacts secrets from administrator technical details', () => {
    expect(
      redactTechnicalError(
        'Authorization: Bearer abc.def.ghi api_key=secret-value client_secret: top-secret sk-1234567890abcdef',
      ),
    ).toBe('Authorization: Bearer •••••••• api_key=•••••••• client_secret: •••••••• sk-••••••••')
  })
})
