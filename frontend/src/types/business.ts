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
  hashtagsJson: string[]
  wordCount: number
  modelName: string
  promptVersion: string
  generationDurationMs: number
  tokenUsage: number
  qualityScore: number
  manualEditRatio: number
  reviewStatus: string
  createdAt: string
}

export interface Schedule {
  id: number
  articleId: number
  variantId: number
  platform: Platform
  articleTitle: string
  variantTitle: string
  scheduledAt: string
  publishMode: 'MOCK' | 'MANUAL'
  status: string
  retryCount: number
  actualPublishAt?: string
  publishedUrl?: string
  errorMessage?: string
  logs?: Array<Record<string, unknown>>
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
