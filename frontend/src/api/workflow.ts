import { apiClient } from '@/api/client'
import type { ApiResponse } from '@/types/api'
import type {
  Article,
  GenerationTask,
  LlmConfig,
  LlmConnectionResult,
  LlmUsage,
  Platform,
  PlatformAccount,
  PublishPackage,
  Schedule,
  Variant,
  MediaAsset,
  WechatFormatProfile,
  WechatThemeProfile,
} from '@/types/business'

async function unwrap<T>(promise: Promise<{ data: ApiResponse<T> }>): Promise<T> {
  return (await promise).data.data
}

export const workflowApi = {
  articles(params: Record<string, unknown> = {}) {
    return unwrap<{ items: Article[]; total: number }>(apiClient.get('/articles', { params }))
  },
  article(id: number) {
    return unwrap<Article>(apiClient.get(`/articles/${id}`))
  },
  createArticle(data: Record<string, unknown>) {
    return unwrap<Article>(apiClient.post('/articles', data))
  },
  updateArticle(id: number, data: Record<string, unknown>) {
    return unwrap<Article>(apiClient.put(`/articles/${id}`, data))
  },
  deleteArticle(id: number) {
    return unwrap<{ id: number }>(apiClient.delete(`/articles/${id}`))
  },
  archiveArticle(id: number) {
    return unwrap<Article>(apiClient.post(`/articles/${id}/archive`))
  },
  variants(id: number) {
    return unwrap<Variant[]>(apiClient.get(`/articles/${id}/variants`))
  },
  updateVariant(id: number, data: Record<string, unknown>) {
    return unwrap<Variant>(apiClient.put(`/variants/${id}`, data))
  },
  wechatFormatProfiles() {
    return unwrap<WechatThemeProfile[]>(apiClient.get('/formatting/wechat/profiles'))
  },
  previewWechatFormat(contentText: string, profile: WechatFormatProfile) {
    return unwrap<{ contentHtml: string; profile: WechatFormatProfile }>(
      apiClient.post('/formatting/wechat/preview', { content_text: contentText, ...profile }),
    )
  },
  formatWechatVariant(id: number, profile: WechatFormatProfile) {
    return unwrap<Variant>(apiClient.put(`/variants/${id}/format`, profile))
  },
  approveVariant(id: number) {
    return unwrap<Variant>(apiClient.post(`/variants/${id}/approve`))
  },
  rejectVariant(id: number) {
    return unwrap<Variant>(apiClient.post(`/variants/${id}/reject`))
  },
  deleteVariant(id: number) {
    return unwrap<{ id: number }>(apiClient.delete(`/variants/${id}`))
  },
  generate(data: Record<string, unknown>) {
    return unwrap<{ taskId: string; status: string }>(apiClient.post('/generation/content', data))
  },
  task(id: string) {
    return unwrap<GenerationTask>(apiClient.get(`/generation/tasks/${id}`))
  },
  retryTaskPlatform(id: string, platform: Platform) {
    return unwrap<{ taskId: string; status: string }>(
      apiClient.post(`/generation/tasks/${id}/platforms/${platform}/retry`),
    )
  },
  reviewVariant(id: number) {
    return unwrap<Record<string, unknown>>(apiClient.post('/generation/review', { article_id: id }))
  },
  regenerate(id: number) {
    return unwrap<{ taskId: string }>(apiClient.post(`/generation/content/${id}/regenerate`))
  },
  keywords(articleId: number) {
    return unwrap<{ keywords: Array<{ zh: string; en: string; reason: string }> }>(
      apiClient.post('/media/extract-keywords', { article_id: articleId }),
    )
  },
  searchMedia(keyword: string) {
    return unwrap<{ items: Array<Record<string, unknown>>; notice: string }>(
      apiClient.get('/media/search', { params: { keyword } }),
    )
  },
  uploadMedia(data: FormData) {
    return unwrap<Record<string, unknown>>(
      apiClient.post('/media/upload', data, { headers: { 'Content-Type': 'multipart/form-data' } }),
    )
  },
  selectMedia(data: Record<string, unknown>) {
    return unwrap<Record<string, unknown>>(apiClient.post('/media/select', data))
  },
  articleMedia(id: number) {
    return unwrap<MediaAsset[]>(apiClient.get(`/articles/${id}/media`))
  },
  recommend(data: { article_id: number; variant_id?: number; platform: Platform }) {
    return unwrap<Record<string, unknown>>(apiClient.post('/recommendations/publish-time', data))
  },
  schedules(params: Record<string, unknown> = {}) {
    return unwrap<Schedule[]>(apiClient.get('/schedules', { params }))
  },
  schedule(id: number) {
    return unwrap<Schedule>(apiClient.get(`/schedules/${id}`))
  },
  createSchedule(data: Record<string, unknown>) {
    return unwrap<Schedule>(apiClient.post('/schedules', data))
  },
  updateSchedule(id: number, data: Record<string, unknown>) {
    return unwrap<Schedule>(apiClient.put(`/schedules/${id}`, data))
  },
  scheduleAction(id: number, action: string, data: Record<string, unknown> = {}) {
    return unwrap<Schedule>(apiClient.post(`/schedules/${id}/${action}`, data))
  },
  dashboard() {
    return unwrap<Record<string, unknown>>(apiClient.get('/dashboard/business'))
  },
  analyticsOverview() {
    return unwrap<Record<string, number>>(apiClient.get('/analytics/overview'))
  },
  analyticsPlatforms() {
    return unwrap<Array<Record<string, number | string>>>(
      apiClient.get('/analytics/platform-comparison'),
    )
  },
  analyticsTimes() {
    return unwrap<Array<Record<string, number | string>>>(
      apiClient.get('/analytics/time-comparison'),
    )
  },
  analyticsRanking() {
    return unwrap<Array<Record<string, number | string>>>(
      apiClient.get('/analytics/content-ranking'),
    )
  },
  analyticsSummary() {
    return unwrap<Record<string, unknown>>(apiClient.post('/analytics/ai-summary'))
  },
  experiments() {
    return unwrap<Array<Record<string, unknown>>>(apiClient.get('/experiments'))
  },
  experiment(id: number) {
    return unwrap<Record<string, unknown>>(apiClient.get(`/experiments/${id}`))
  },
  createExperiment(data: Record<string, unknown>) {
    return unwrap<Record<string, unknown>>(apiClient.post('/experiments', data))
  },
  experimentAction(id: number, action: string) {
    return unwrap<Record<string, unknown>>(apiClient.post(`/experiments/${id}/${action}`))
  },
  users() {
    return unwrap<Array<Record<string, unknown>>>(apiClient.get('/admin/users'))
  },
  auditLogs() {
    return unwrap<Array<Record<string, unknown>>>(apiClient.get('/admin/audit-logs'))
  },
  settings() {
    return unwrap<Array<Record<string, unknown>>>(apiClient.get('/settings'))
  },
  updateSetting(key: string, value: string) {
    return unwrap<Record<string, unknown>>(apiClient.put(`/settings/${key}`, { value }))
  },
  llmConfig() {
    return unwrap<LlmConfig>(apiClient.get('/settings/model-service'))
  },
  saveLlmConfig(data: LlmConfig) {
    return unwrap<LlmConfig>(
      apiClient.put('/settings/model-service', {
        provider: data.provider,
        base_url: data.baseUrl,
        api_key: data.apiKey,
        model: data.model,
        input_price_per_million: data.inputPricePerMillion,
        output_price_per_million: data.outputPricePerMillion,
        currency: data.currency,
      }),
    )
  },
  testLlmConnection(data: LlmConfig) {
    return unwrap<LlmConnectionResult>(
      apiClient.post('/settings/model-service/test', {
        provider: data.provider,
        base_url: data.baseUrl,
        api_key: data.apiKey,
        model: data.model,
        input_price_per_million: data.inputPricePerMillion,
        output_price_per_million: data.outputPricePerMillion,
        currency: data.currency,
      }),
    )
  },
  llmUsage(days = 30) {
    return unwrap<LlmUsage>(apiClient.get('/settings/model-service/usage', { params: { days } }))
  },
  platformAccounts() {
    return unwrap<PlatformAccount[]>(apiClient.get('/platform-accounts'))
  },
  savePlatformAccount(platform: Platform, data: Record<string, unknown>) {
    return unwrap<PlatformAccount>(apiClient.put(`/platform-accounts/${platform}`, data))
  },
  testPlatformAccount(platform: Platform) {
    return unwrap<PlatformAccount & { result: Record<string, unknown> }>(
      apiClient.post(`/platform-accounts/${platform}/test`),
    )
  },
  disconnectPlatformAccount(platform: Platform) {
    return unwrap<PlatformAccount>(apiClient.delete(`/platform-accounts/${platform}`))
  },
  platformAuthLogs(platform: Platform) {
    return unwrap<Array<Record<string, unknown>>>(
      apiClient.get(`/platform-accounts/${platform}/auth-logs`),
    )
  },
  startWeiboOAuth(redirectUri: string) {
    return unwrap<{ authorizationUrl: string }>(
      apiClient.post('/platform-accounts/WEIBO/oauth/start', { redirect_uri: redirectUri }),
    )
  },
  publishPackage(id: number) {
    return unwrap<PublishPackage>(apiClient.get(`/schedules/${id}/publish-package`))
  },
  async downloadPublishPackage(id: number) {
    const response = await apiClient.get(`/schedules/${id}/publish-package/download`, {
      responseType: 'blob',
    })
    const url = URL.createObjectURL(response.data)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `xiaohongshu-${id}.zip`
    anchor.click()
    URL.revokeObjectURL(url)
  },
}
