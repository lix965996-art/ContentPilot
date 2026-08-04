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
  coverThumbnailUrl?: string
  createdAt: string
  updatedAt: string
  variants?: Variant[]
}

export interface ArticleEngagementMetric {
  scheduleId: number
  platform: Platform
  metricDate: string
  impressions: number
  likes: number
  comments: number
  collects: number
  shares: number
  followers: number
  engagementTotal: number
  engagementRate: number
  dataSource: string
}

export interface ArticleEngagementTotals {
  impressions: number
  likes: number
  comments: number
  collects: number
  shares: number
  engagementTotal: number
  engagementRate: number
}

export interface ArticleEngagementSummary {
  articleId: number
  hasData: boolean
  platforms?: ArticleEngagementMetric[]
  totals: ArticleEngagementTotals | null
  dataSources: string[]
  simulated: boolean
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

export type TimeSource = 'RECOMMENDED' | 'ALTERNATIVE' | 'CUSTOM'

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
  recommendationId?: number
  recommendedAt?: string
  timeSource: TimeSource
  contentType?: string
  contentTypeName?: string
  timeDeviationMinutes?: number | null
  usedRecommendedTime?: boolean
  recommendationSnapshotJson?: Record<string, unknown>
}

export interface RecommendationReason {
  type: string
  description: string
  contribution: number
}

export interface RecommendationAlternative {
  recommendedAt: string
  score: number
  confidence: string
  sampleCount: number
  reason: string
}

export interface ScheduleConflict {
  scheduleId: number
  articleTitle?: string
  scheduledAt: string
  minutes: number
  sameAccount: boolean
  level: 'CONFLICT' | 'DENSITY'
  message: string
}

export type TimeWindow = '30D' | '90D' | 'ALL' | 'CUSTOM'

export interface TimeWindowInfo {
  window: TimeWindow
  label: string
  startDate: string | null
  endDate: string | null
  sufficient: boolean
  message: string
  sampleCount?: number
  accountSampleCount?: number
  baselineSampleCount?: number
}

export interface ActivityCurvePoint {
  hour: number
  time: string
  platformPrior: number
  accountHistory: number | null
  publicBaseline: number | null
  sampleCount: number
}

export interface PublishTimeRecommendation {
  id: number
  articleId: number
  variantId?: number
  platform: Platform
  accountId?: number
  recommendedAt: string
  score: number
  confidence: 'HIGH' | 'MEDIUM' | 'LOW'
  algorithmVersion: string
  contentType?: string
  contentTypeName?: string
  contentTypeProvider?: string
  topic?: string
  audience?: string
  sampleCount: number
  accountSampleCount: number
  baselineSampleCount: number
  reasons: RecommendationReason[]
  alternatives: RecommendationAlternative[]
  warnings: string[]
  conflicts: ScheduleConflict[]
  weights: { baseline: number; history: number; content: number; timezone: number }
  dataSource: {
    baseline: string
    accountHistory: string
    priorRuleCount: number
    publicSampleCount: number
    accountSampleCount: number
    sourceTypes: Array<{ sourceType: string; label: string; count: number }>
  }
  dataSufficiency: {
    level: string
    accountSamples: number
    slotSamples: number
    sufficient: boolean
    message: string
  }
  narrative?: string
  narrativeProvider?: string
  window?: TimeWindowInfo
  curve: ActivityCurvePoint[]
}

export interface ActivityBucket {
  sampleCount: number
  score: number
  engagementRate: number
  avgViews: number
  avgLikes: number
  avgComments: number
  avgShares: number
  avgFavorites: number
}

export interface ExperimentSampleRow {
  id: number
  experimentId: number
  scheduleId?: number
  groupType: 'CONTROL' | 'TREATMENT'
  sampleLabel: string
  metricValueJson: Record<string, unknown>
  assignmentSource?: 'AUTO' | 'MANUAL'
  assignmentReason?: string | null
  createdAt: string
}

export interface ActivityAnalysis {
  filters: Record<string, unknown>
  windowInfo?: TimeWindowInfo
  sampleCount: number
  accountSampleCount: number
  baselineSampleCount: number
  globalMeanScore: number
  weekday: Array<ActivityBucket & { dayOfWeek: number; name: string }>
  hourly: Array<ActivityBucket & { hour: number; time: string }>
  heatmap: Array<{
    dayOfWeek: number
    name: string
    hour: number
    sampleCount: number
    score: number
  }>
  contentTypes: Array<
    ActivityBucket & {
      contentType: string
      contentTypeName: string
      bestSlots: Array<{
        dayOfWeek: number
        dayName: string
        hour: number
        time: string
        sampleCount: number
        score: number
      }>
    }
  >
  topSlots: Array<{
    dayOfWeek: number
    dayName: string
    hour: number
    time: string
    sampleCount: number
    score: number
    rawScore: number
  }>
  completeness: {
    score: number
    fields: Array<{
      field: string
      label: string
      filled: number
      total: number
      percent: number
    }>
    dateRange: { start: string | null; end: string | null }
  }
  sources: Array<{ sourceType: string; label: string; count: number }>
  scoreFormula: string
  notice: string
}

export interface HistoryImportPreview {
  filename: string
  headers: string[]
  mapping: Record<string, string>
  fields: Array<{ field: string; label: string; required: boolean; type: string }>
  totalRows: number
  validRows: number
  errorRows: number
  duplicateInFile: number
  duplicateInDatabase: number
  missingValueRows: number
  importableRows: number
  errors: Array<{ row: number; message: string }>
  preview: Array<Record<string, unknown>>
  sourceTypes: Array<{ value: string; label: string }>
}

export interface HistoryImportBatch {
  id: number
  filename: string
  sourceType: string
  sourceLabel: string
  sourceNote?: string
  platformHint?: string
  totalRows: number
  successCount: number
  duplicateCount: number
  errorCount: number
  missingValueCount: number
  status: string
  remainingRows?: number
  errorsJson?: Array<{ row: number; message: string }>
  createdAt: string
}

export interface RecommendationEffect {
  adoption: {
    totalSchedules: number
    withRecommendation: number
    adoptedCount: number
    adoptionRate: number
    averageDeviationMinutes: number
    deviationBuckets: Array<{ name: string; count: number }>
  }
  comparison: Array<{
    name: string
    scheduleCount: number
    measuredCount: number
    impressions: number
    engagementTotal: number
    engagementRate: number
    avgEngagementRate: number
  }>
  experimentGroups: RecommendationEffect['comparison']
  items: Array<{
    scheduleId: number
    title: string
    platform: Platform
    status: string
    timeSource: TimeSource
    contentType?: string
    scheduledAt: string
    recommendedAt: string | null
    actualPublishAt: string | null
    deviationMinutes: number | null
    executionDelayMinutes: number | null
    sampleCount: number
    impressions: number
    engagementTotal: number
    engagementRate: number
  }>
  notice: string
}

export interface DecisionComponent {
  type: string
  label: string
  weight: number
  rawScore: number
  contribution: number
  description: string
}

/** Full "why this time" chain for one schedule: content → analysis → decision → result. */
export interface PublishDecisionChain {
  scheduleId: number
  title: string
  platform: Platform
  status: string
  explainSource: 'SNAPSHOT' | 'RECOMPUTED'
  explainNotice: string
  content: {
    articleTitle: string | null
    variantTitle: string | null
    contentType: string
    contentTypeName: string
    contentTypeProvider: 'STORED' | 'RULE'
    modelName: string | null
    promptVersion: string | null
    wordCount: number | null
    emojiCount: number | null
    hashtags: string[]
    generationDurationMs: number | null
    tokenUsage: number | null
  }
  analysis: {
    algorithmVersion: string
    weekday: number
    weekdayName: string
    hour: number
    score: number
    confidence: 'HIGH' | 'MEDIUM' | 'LOW'
    weights: { baseline: number; history: number; content: number; timezone: number }
    components: DecisionComponent[]
    hourly: Array<{ hour: number; score: number }>
    bestHour: number
    bestHourScore: number
    accountSampleCount: number
    baselineSampleCount: number
    contentSampleCount: number
    window: { window: string; label: string }
    sourceTypes: Array<{ sourceType: string; label: string; count: number }>
  }
  decision: {
    recommendedAt: string | null
    scheduledAt: string
    actualPublishAt: string | null
    timeSource: TimeSource
    timeSourceLabel: string
    deviationMinutes: number | null
    snapshotScore: number | null
    snapshotConfidence: string | null
    narrative: string | null
    alternatives: RecommendationAlternative[]
  }
  result: {
    sampleCount: number
    impressions: number
    engagementTotal: number
    engagementRate: number | null
    dataSources: string[]
  }
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

/** Extended labels for activity analysis (includes public research datasets). */
export const analysisPlatformNames: Record<string, string> = {
  ...platformNames,
  YOUTUBE: 'YouTube（公开样本）',
}

export const platformColors: Record<Platform, string> = {
  WEIBO: '#f59e0b',
  XIAOHONGSHU: '#ef4444',
  WECHAT_OFFICIAL: '#16a34a',
  TOUTIAO: '#f04438',
  X: '#111827',
}
