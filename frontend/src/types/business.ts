export type Platform = 'WEIBO' | 'XIAOHONGSHU' | 'WECHAT_OFFICIAL'

export interface Article {
  id: number
  title: string
  sourceText: string
  summary?: string
  topic?: string
  targetAudience?: string
  tone?: string
  keywords: string[]
  status: string
  variantCount: number
  createdAt: string
  updatedAt: string
  variants?: Variant[]
}

export interface Variant {
  id: number
  articleId: number
  platform: Platform
  versionNo: number
  title: string
  contentText: string
  contentHtml?: string
  formatProfileJson?: WechatFormatProfile
  hashtagsJson: string[]
  wordCount: number
  modelName: string
  promptVersion: string
  generationDurationMs: number
  tokenUsage: number
  promptTokens: number
  completionTokens: number
  estimatedCost: number
  qualityScore: number
  manualEditRatio: number
  reviewStatus: string
  reviewDetailJson?: Record<string, unknown>
  createdAt: string
}

export interface WechatFormatProfile {
  theme: 'clean' | 'brand' | 'editorial'
  accent_color: string
  font_size: number
  line_height: number
  paragraph_spacing: number
  first_line_indent: boolean
  link_footnotes: boolean
}

export interface WechatThemeProfile {
  key: WechatFormatProfile['theme']
  name: string
  description: string
  accent_color: string
  heading_style: string
  quote_background: string
}

export type GenerationPlatformStatus = 'PENDING' | 'RUNNING' | 'RETRYING' | 'SUCCESS' | 'FAILED'

export interface GenerationPlatformProgress {
  status: GenerationPlatformStatus
  progress: number
  attempt: number
  variantId?: number
  error?: string
  durationMs: number
  tokenUsage: number
}

export interface GenerationTask {
  id: string
  articleId: number
  status: 'PENDING' | 'RUNNING' | 'SUCCESS' | 'PARTIAL_SUCCESS' | 'FAILED'
  progress: number
  platformsJson: Platform[]
  platformStatusJson: Partial<Record<Platform, GenerationPlatformProgress>>
  resultVariantIdsJson: number[]
  variants: Variant[]
  provider: string
  modelName: string
  promptVersion: string
  tokenUsage: number
  durationMs: number
  errorMessage?: string
}

export interface MediaAsset {
  id: number
  articleId: number
  variantId?: number
  imageUrl: string
  thumbnailUrl: string
  altText?: string
  usageType: 'COVER' | 'BODY'
  source: string
  selected: boolean
}

export interface Schedule {
  id: number
  articleId: number
  variantId: number
  platform: Platform
  articleTitle: string
  variantTitle: string
  scheduledAt: string
  accountId: number
  accountName: string
  publishMode: PublishMode
  status: string
  retryCount: number
  actualPublishAt?: string
  publishedUrl?: string
  externalId?: string
  resultMode?: string
  publishPackageJson?: PublishPackage
  errorMessage?: string
  logs?: Array<Record<string, unknown>>
}

export type PublishMode = 'REAL_API' | 'DRAFT_ONLY' | 'MANUAL_CONFIRM'

export type PlatformAccountStatus =
  | 'NOT_CONFIGURED'
  | 'CONNECTING'
  | 'CONNECTED'
  | 'TOKEN_EXPIRED'
  | 'INVALID'
  | 'DISABLED'
  | 'MANUAL_ONLY'

export interface PlatformAccount {
  id: number | null
  platform: Platform
  platformName: string
  accountName: string
  authType: 'NONE' | 'OAUTH2' | 'APP_SECRET'
  publishMode: PublishMode | 'SUBMIT_PUBLISH'
  status: PlatformAccountStatus
  capabilities: string[]
  lastTestAt?: string
  lastError?: string
  appId: string
  clientId: string
  secretConfigured: boolean
  accessTokenConfigured: boolean
  refreshTokenConfigured: boolean
  tokenHint: string
  tokenExpiresAt?: string
  config: {
    redirect_uri?: string
    default_author?: string
    default_cover_media_id?: string
    default_cover_url?: string
    allow_submit_publish?: boolean
  }
  connectionGuide: {
    mode: 'OFFICIAL_OAUTH' | 'APP_SECRET' | 'MANUAL_ONLY'
    consoleUrl: string
    callbackPath?: string
    steps: string[]
  }
}

export interface PublishPackage {
  title: string
  content: string
  hashtags: string[]
  coverImage?: string
  images: string[]
  imageOrder: number[]
  creatorUrl: string
  notice: string
}

export interface LlmConfig {
  provider: string
  baseUrl: string
  apiKey: string
  apiKeyConfigured: boolean
  model: string
  inputPricePerMillion: number
  outputPricePerMillion: number
  currency: 'CNY' | 'USD'
}

export interface LlmConnectionResult {
  connected: boolean
  latencyMs: number
  models: string[]
  message: string
}

export interface LlmUsage {
  days: number
  generations: number
  promptTokens: number
  completionTokens: number
  totalTokens: number
  estimatedCost: number
  averageTokens: number
  currency: 'CNY' | 'USD'
  byModel: Array<{ model: string; generations: number; tokens: number; cost: number }>
  daily: Array<{ date: string; tokens: number; cost: number }>
}

export const platformNames: Record<Platform, string> = {
  WEIBO: '微博',
  XIAOHONGSHU: '小红书',
  WECHAT_OFFICIAL: '微信公众号',
}

export const platformColors: Record<Platform, string> = {
  WEIBO: '#f59e0b',
  XIAOHONGSHU: '#ef4444',
  WECHAT_OFFICIAL: '#16a34a',
}
