import { apiClient } from './client'

import type { ApiResponse } from '@/types/api'
import type { AuthData, LoginPayload, User } from '@/types/user'

export async function login(payload: LoginPayload): Promise<AuthData> {
  const response = await apiClient.post<ApiResponse<AuthData>>('/auth/login', payload)
  return response.data.data
}

export async function fetchCurrentUser(): Promise<User> {
  const response = await apiClient.get<ApiResponse<User>>('/auth/me')
  return response.data.data
}

export async function logout(): Promise<void> {
  await apiClient.post('/auth/logout')
}
