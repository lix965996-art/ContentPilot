export type Platform = 'WEIBO' | 'XIAOHONGSHU' | 'WECHAT_OFFICIAL' | 'TOUTIAO' | 'X'

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

export interface DeepCreationCandidate {
  title: string
  content: string
  hashtags: string[]
  warnings?: string[]
  summary?: string
  cover_text?: string
  cover_prompt?: string
  author?: string
}

export interface GenerationPlatformProgress {
  status: GenerationPlatformStatus
  progress: number
  stage?: string
  message?: string
  attempt: number
  maxAttempts?: number
  variantId?: number
  error?: string
  durationMs: number
  tokenUsage: number
  updatedAt?: string
  brief?: Record<string, unknown>
  strategy?: {
    angle: string
    hook: string
    reader_value: string
    structure: string[]
    cta: string
  }
  review?: Record<string, unknown>
  candidateTitles?: string[]
  candidates?: DeepCreationCandidate[]
  selectedCandidate?: number
  userSelectedCandidate?: number
  userSelectedVariantId?: number
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
  createdAt?: string
  updatedAt?: string
  optionsJson?: Record<string, unknown>
}

export interface TrendItem {
  id: string
  source: 'BAIDU' | 'HACKER_NEWS'
  sourceName: string
  rank: number
  title: string
  summary: string
  url: string
  imageUrl?: string
  heat?: number
  heatLabel: string
  fetchedAt: string
  tags: string[]
}

export interface TrendAngle {
  title: string
  audience: string
  hook: string
  outline: string[]
  creative_goal: string
}

export interface TrendAnalysis {
  relevance_reason: string
  recommended_angle_index: number
  angles: TrendAngle[]
  risk_notes: string[]
  verification_questions: string[]
  provider: string
  modelName: string
  tokenUsage: number
}

export interface MediaAsset {
  id: number
  articleId?: number
  articleTitle?: string
  variantId?: number
  imageUrl: string
  thumbnailUrl: string
  altText?: string
  usageType: 'COVER' | 'BODY'
  source: string
  selected: boolean
  title?: string
  collection?: string
  tags: string[]
  favorite: boolean
  licenseType?: string
  licenseNote?: string
  photographerName?: string
  photographerUrl?: string
  createdAt: string
}

export interface ResearchItem {
  id: number
  title: string
  summary?: string
  url?: string
  imageUrl?: string
  source: string
  sourceName?: string
  sourceId?: string
  topicCluster?: string
  tags: string[]
  notes?: string
  status: 'INBOX' | 'RESEARCHING' | 'READY' | 'USED'
  archived: boolean
  createdAt: string
  updatedAt: string
}

export interface ScheduleBacklogItem {
  articleId: number
  variantId: number
  articleTitle: string
  variantTitle: string
  platform: Platform
  reviewStatus: string
  coverReady: boolean
  accountReady: boolean
  ready: boolean
  blockers: string[]
  updatedAt: string
}

export interface OperationStep {
  key: string
  name: string
  status: string
  stage?: string
  message?: string
  progress: number
  durationMs: number
  tokenUsage?: number
  error?: string
  attempt?: number
  createdAt?: string
}

export interface OperationRun {
  id: string
  sourceId: string | number
  type: 'GENERATION' | 'PUBLISH'
  title: string
  subtitle: string
  status: string
  progress: number
  provider?: string
  modelName?: string
  tokenUsage?: number
  durationMs: number
  errorMessage?: string
  createdAt: string
  updatedAt: string
  scheduledAt?: string
  retryCount?: number
  maxRetryCount?: number
  steps: OperationStep[]
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

export type PublishMode =
  | 'REAL_API'
  | 'DRAFT_ONLY'
  | 'SUBMIT_PUBLISH'
  | 'MANUAL_CONFIRM'
  | 'CDP_PUBLISH'
  | 'MCP_PUBLISH'
  | 'BROWSER_PUBLISH'
  | 'BROWSER_DRAFT'
  | 'WECHATSYNC_CLI'

export type PlatformAccountStatus =
  | 'NOT_CONFIGURED'
  | 'CONNECTING'
  | 'CONNECTED'
  | 'TOKEN_EXPIRED'
  | 'INVALID'
  | 'DISABLED'
  | 'MANUAL_ONLY'
  | 'READY'
  | 'LOGIN_REQUIRED'

export interface PlatformAccount {
  id: number | null
  platform: Platform
  platformName: string
  accountName: string
  authType: 'NONE' | 'OAUTH2' | 'APP_SECRET' | 'QR_LOGIN'
  publishMode: PublishMode
  status: PlatformAccountStatus
  capabilities: string[]
  publishHint: string
  lastTestAt?: string
  lastError?: string
  loginUsername?: string
  lastLoginAt?: string
  sessionDurationSeconds?: number
  appId: string
  clientId: string
  secretConfigured: boolean
  accessTokenConfigured: boolean
  refreshTokenConfigured: boolean
  tokenHint: string
  tokenExpiresAt?: string
  localPublishingEnabled: boolean
  publicPublishEnabled: boolean
  availablePublishModes: PublishMode[]
  config: {
    redirect_uri?: string
    operation_ip?: string
    default_author?: string
    default_cover_media_id?: string
    default_cover_url?: string
    allow_submit_publish?: boolean
    allow_public_publish?: boolean
  }
  connectionGuide: {
    mode:
      | 'OFFICIAL_OAUTH'
      | 'OFFICIAL_OAUTH2_PKCE'
      | 'APP_SECRET'
      | 'MANUAL_ONLY'
      | 'MANUAL_DELIVERY'
      | 'LOCAL_BROWSER_QR'
    consoleUrl: string
    callbackPath?: string
    steps: string[]
  }
  shared?: boolean
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
  monthlyBudget: number
  budgetWarningPercent: number
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
  pricedGenerations: number
  unpricedGenerations: number
  promptTokens: number
  completionTokens: number
  totalTokens: number
  estimatedCost: number
  averageTokens: number
  currency: 'CNY' | 'USD'
  priceConfigured: boolean
  inputPricePerMillion: number
  outputPricePerMillion: number
  monthlyBudget: number
  monthlyCost: number
  budgetWarningPercent: number
  budgetUsedPercent: number
  budgetAlert: boolean
  byModel: Array<{
    model: string
    generations: number
    tokens: number
    cost: number
    unpricedGenerations: number
  }>
  daily: Array<{
    date: string
    tokens: number
    cost: number
    unpricedGenerations: number
  }>
  recent: Array<{
    id: number
    articleTitle: string
    platform: Platform
    model: string
    promptTokens: number
    completionTokens: number
    totalTokens: number
    cost: number | null
    pricingStatus: 'CURRENT_PRICE' | 'SAVED_ESTIMATE' | 'UNPRICED' | 'NO_USAGE'
    createdAt: string
  }>
}

export const platformNames: Record<Platform, string> = {
  WEIBO: '微博',
  XIAOHONGSHU: '小红书',
  WECHAT_OFFICIAL: '微信公众号',
  TOUTIAO: '今日头条',
  X: 'X',
}

export const platformColors: Record<Platform, string> = {
  WEIBO: '#f59e0b',
  XIAOHONGSHU: '#ef4444',
  WECHAT_OFFICIAL: '#16a34a',
  TOUTIAO: '#f04438',
  X: '#111827',
}
