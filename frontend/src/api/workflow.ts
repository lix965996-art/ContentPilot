import { apiClient } from '@/api/client'
import type { ApiResponse } from '@/types/api'
import type { Article, Platform, Schedule, Variant } from '@/types/business'

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
  approveVariant(id: number) {
    return unwrap<Variant>(apiClient.post(`/variants/${id}/approve`))
  },
  generate(data: Record<string, unknown>) {
    return unwrap<{ taskId: string; status: string }>(apiClient.post('/generation/content', data))
  },
  task(id: string) {
    return unwrap<Record<string, unknown> & { variants?: Variant[] }>(
      apiClient.get(`/generation/tasks/${id}`),
    )
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
    return unwrap<Array<Record<string, unknown>>>(apiClient.get(`/articles/${id}/media`))
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
}
