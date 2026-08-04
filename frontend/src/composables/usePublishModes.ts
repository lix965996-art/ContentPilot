import type { Platform, PlatformAccount, PublishMode } from '@/types/business'

export const publishModeNames: Record<PublishMode, string> = {
  REAL_API: '官方 API 发布',
  DRAFT_ONLY: '同步到草稿箱',
  SUBMIT_PUBLISH: '提交平台发布',
  MANUAL_CONFIRM: '人工发布确认',
  CDP_PUBLISH: '浏览器自动发布',
  MCP_PUBLISH: '本机自动发布',
  BROWSER_PUBLISH: '本机浏览器发布',
  BROWSER_DRAFT: '本机浏览器保存草稿',
  WECHATSYNC_CLI: 'Wechatsync CLI',
}

export const accountStatusNames: Record<string, string> = {
  NOT_CONFIGURED: '未配置',
  CONNECTING: '待授权验证',
  CONNECTED: '已连接',
  TOKEN_EXPIRED: '授权已过期',
  INVALID: '连接无效',
  DISABLED: '已停用',
  MANUAL_ONLY: '仅人工交付',
  READY: '已就绪',
  LOGIN_REQUIRED: '需要登录',
}

export function canUseXiaohongshuMcp(account?: PlatformAccount): boolean {
  return Boolean(
    account?.localPublishingEnabled &&
    account.availablePublishModes.includes('MCP_PUBLISH') &&
    account.publishMode === 'MCP_PUBLISH' &&
    account.status === 'CONNECTED',
  )
}

export function canUseXApi(account?: PlatformAccount): boolean {
  return Boolean(
    account?.status === 'CONNECTED' &&
    account.availablePublishModes.includes('REAL_API') &&
    account.publicPublishEnabled,
  )
}

export function defaultPublishMode(platform: Platform, account?: PlatformAccount): PublishMode {
  if (platform === 'TOUTIAO') return 'BROWSER_PUBLISH'
  if (platform === 'XIAOHONGSHU') {
    return canUseXiaohongshuMcp(account) ? 'MCP_PUBLISH' : 'MANUAL_CONFIRM'
  }
  if (platform === 'X') return 'REAL_API'
  if (platform === 'WECHAT_OFFICIAL') {
    return account?.publishMode === 'BROWSER_DRAFT' ? 'BROWSER_DRAFT' : 'DRAFT_ONLY'
  }
  return 'REAL_API'
}

export interface PublishModeOption {
  value: PublishMode
  label: string
  disabled?: boolean
}

export function publishModeOptions(
  platform: Platform,
  account?: PlatformAccount,
): PublishModeOption[] {
  if (platform === 'XIAOHONGSHU')
    return [
      { value: 'MANUAL_CONFIRM', label: '人工发布后确认（默认）' },
      ...(account?.localPublishingEnabled
        ? [
            {
              value: 'MCP_PUBLISH' as PublishMode,
              label: '本机自动发布（仅自己可见）',
              disabled: !canUseXiaohongshuMcp(account),
            },
          ]
        : []),
    ]
  if (platform === 'WECHAT_OFFICIAL')
    return [
      ...(account?.availablePublishModes.includes('BROWSER_DRAFT')
        ? [
            {
              value: 'BROWSER_DRAFT' as PublishMode,
              label: '本机扫码保存到草稿箱',
              disabled: account?.status !== 'CONNECTED' || account.publishMode !== 'BROWSER_DRAFT',
            },
          ]
        : []),
      { value: 'DRAFT_ONLY', label: '自动进入草稿箱', disabled: account?.status !== 'CONNECTED' },
      {
        value: 'REAL_API',
        label: '提交发布',
        disabled: account?.status !== 'CONNECTED' || account.publishMode !== 'SUBMIT_PUBLISH',
      },
    ]
  if (platform === 'TOUTIAO')
    return [
      {
        value: 'BROWSER_PUBLISH',
        label: '本机浏览器发布（真实文章）',
        disabled:
          account?.status !== 'CONNECTED' ||
          account.publishMode !== 'BROWSER_PUBLISH' ||
          !account.publicPublishEnabled,
      },
    ]
  if (platform === 'X')
    return [{ value: 'REAL_API', label: 'X 官方 API（真实发布）', disabled: !canUseXApi(account) }]
  return [{ value: 'REAL_API', label: '微博官方 API', disabled: account?.status !== 'CONNECTED' }]
}

export function publishModeLabel(platform: Platform, mode: PublishMode): string {
  if (platform === 'WEIBO' && mode === 'REAL_API') return '微博官方 API'
  if (platform === 'X' && mode === 'REAL_API') return 'X 官方 API（真实发布）'
  return publishModeNames[mode] || mode
}

/** Format a Date as the local `YYYY-MM-DDTHH:mm:ss` string the API expects. */
export function formatLocalDateTime(value: Date): string {
  const offset = value.getTimezoneOffset() * 60_000
  return new Date(value.getTime() - offset).toISOString().slice(0, 19)
}
