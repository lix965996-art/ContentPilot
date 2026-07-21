import { apiClient } from './client'

import type { ApiResponse } from '@/types/api'
import type { DashboardSummary } from '@/types/dashboard'

export async function fetchDashboardSummary(): Promise<DashboardSummary> {
  const response = await apiClient.get<ApiResponse<DashboardSummary>>('/dashboard/summary')
  return response.data.data
}
