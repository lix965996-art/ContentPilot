export type OperationErrorAction = 'platform-accounts' | 'media' | 'studio' | 'settings'

export interface OperationErrorPresentation {
  title: string
  description: string
  primaryAction?: OperationErrorAction
  primaryActionLabel?: string
  secondaryAction?: OperationErrorAction
  secondaryActionLabel?: string
  retryRecommended: boolean
}

interface OperationErrorContext {
  type?: 'GENERATION' | 'PUBLISH'
  platform?: string
}

function includesAny(value: string, patterns: RegExp[]) {
  return patterns.some((pattern) => pattern.test(value))
}

export function presentOperationError(
  rawError: string | undefined,
  context: OperationErrorContext = {},
): OperationErrorPresentation | undefined {
  if (!rawError?.trim()) return undefined

  const value = rawError.toLowerCase()
  const isWechat =
    /wechat|公众号|素材上传|media_id|default_cover/.test(value) ||
    context.platform?.includes('WECHAT_OFFICIAL')

  if (
    context.type === 'GENERATION' &&
    includesAny(value, [
      /api unauthorized/,
      /\bunauthori[sz]ed\b/,
      /api.?key.{0,12}(?:invalid|expired|无效|过期|失效)/,
      /access.?token/,
    ])
  ) {
    return {
      title: 'AI 模型服务授权异常',
      description: '模型服务的 API Key 可能无效或已过期。请联系管理员检查模型服务配置。',
      primaryAction: 'settings',
      primaryActionLabel: '前往模型设置',
      retryRecommended: false,
    }
  }

  if (
    includesAny(value, [
      /\b48001\b/,
      /api unauthorized/,
      /\bunauthori[sz]ed\b/,
      /token.{0,12}(?:expired|过期|失效)/,
      /access.?token/,
      /授权.{0,8}(?:失效|过期|异常)/,
    ])
  ) {
    return {
      title: isWechat ? '公众号素材接口未授权' : '平台授权已失效',
      description: isWechat
        ? '公众号授权可能已失效，或当前账号没有素材上传权限。请先重新验证公众号连接，再检查封面素材。'
        : '当前平台连接可能已过期或权限不足。请先重新完成平台授权。',
      primaryAction: 'platform-accounts',
      primaryActionLabel: '前往平台账号设置',
      secondaryAction: isWechat ? 'media' : undefined,
      secondaryActionLabel: isWechat ? '检查封面素材' : undefined,
      retryRecommended: false,
    }
  }

  if (
    includesAny(value, [
      /default_cover_media_id/,
      /cover_media_id/,
      /封面素材/,
      /封面图片/,
      /素材上传失败/,
    ])
  ) {
    return {
      title: '封面素材未准备好',
      description: '请配置默认封面素材，或在文章中选择一张本地图片作为封面，然后再发布。',
      primaryAction: 'media',
      primaryActionLabel: '检查封面素材',
      secondaryAction: 'studio',
      secondaryActionLabel: '返回内容工作室',
      retryRecommended: false,
    }
  }

  if (includesAny(value, [/\b429\b/, /rate.?limit/, /too many requests/, /请求.{0,6}频繁/])) {
    return {
      title: '平台请求过于频繁',
      description: '平台暂时限制了请求频率。请稍等片刻后再重试。',
      retryRecommended: true,
    }
  }

  if (
    includesAny(value, [
      /timeout/,
      /timed out/,
      /network/,
      /connection/,
      /请求超时/,
      /网络异常/,
      /连接失败/,
    ])
  ) {
    return {
      title: '平台连接暂时不可用',
      description: '网络或平台服务暂时没有响应。请确认网络正常后重试。',
      retryRecommended: true,
    }
  }

  if (
    includesAny(value, [
      /格式校验/,
      /格式不合规/,
      /正文.{0,8}(?:过长|超出|超过)/,
      /content.{0,8}(?:length|limit)/,
      /validation/,
    ])
  ) {
    return {
      title: '内容格式未通过平台校验',
      description: '当前内容可能超过平台限制或格式不符合要求。请返回内容工作室调整后再试。',
      primaryAction: 'studio',
      primaryActionLabel: '返回内容工作室',
      retryRecommended: context.type === 'GENERATION',
    }
  }

  return {
    title: context.type === 'PUBLISH' ? '本次发布未完成' : '本次创作未完成',
    description:
      context.type === 'PUBLISH'
        ? '平台没有完成本次发布。请先检查平台连接和内容设置，再尝试重新发布。'
        : '系统没有完成本次内容生成。你可以重新尝试，其他平台已成功的结果不会受影响。',
    retryRecommended: true,
  }
}

export function redactTechnicalError(rawError: string) {
  return rawError
    .replace(
      /\bAuthorization\s*:\s*Bearer\s+[A-Za-z0-9._~+/=-]+/gi,
      'Authorization: Bearer ••••••••',
    )
    .replace(/\bBearer\s+[A-Za-z0-9._~+/=-]+/gi, 'Bearer ••••••••')
    .replace(
      /\b(api[_ -]?key|client[_ -]?secret|access[_ -]?token|refresh[_ -]?token)(\s*[:=]\s*)([^,;\s\n]+)/gi,
      '$1$2••••••••',
    )
    .replace(/\bsk-[A-Za-z0-9_-]{8,}\b/g, 'sk-••••••••')
}
