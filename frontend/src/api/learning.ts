import { apiClient } from '@/api/client'
import type { ApiResponse } from '@/types/api'
import type { LearningStatus } from '@/types/learning'

export const learningApi = {
  async status(): Promise<LearningStatus> {
    return (await apiClient.get<ApiResponse<LearningStatus>>('/learning/status')).data.data
  },
  async collect(
    scheduleId: number,
    requestKey: string,
  ): Promise<{ taskId: string; status: string }> {
    return (
      await apiClient.post<ApiResponse<{ taskId: string; status: string }>>(
        `/learning/collect/${scheduleId}`,
        { request_key: requestKey },
      )
    ).data.data
  },
  async activate(platform: string, modelId: string | null): Promise<void> {
    await apiClient.post('/learning/models/activate', { platform, model_id: modelId })
  },
}
