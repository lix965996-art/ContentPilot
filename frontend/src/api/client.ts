import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios'

import type { ApiResponse } from '@/types/api'
import type { AuthData } from '@/types/user'

const ACCESS_TOKEN_KEY = 'contentpilot_access_token'
const REFRESH_TOKEN_KEY = 'contentpilot_refresh_token'
const LEGACY_ACCESS_TOKEN_KEY = 'socialflow_access_token'
const LEGACY_REFRESH_TOKEN_KEY = 'socialflow_refresh_token'
const REFRESH_TIMEOUT = 15_000

interface RetryRequestConfig extends InternalAxiosRequestConfig {
  _retry?: boolean
}

export const apiClient = axios.create({
  baseURL: '/api',
  timeout: 15_000,
  headers: { 'Content-Type': 'application/json' },
})

export function readAccessToken(): string | null {
  const token = localStorage.getItem(ACCESS_TOKEN_KEY) || sessionStorage.getItem(ACCESS_TOKEN_KEY)
  if (token) return token
  const legacyToken = localStorage.getItem(LEGACY_ACCESS_TOKEN_KEY)
  if (legacyToken) {
    localStorage.setItem(ACCESS_TOKEN_KEY, legacyToken)
    localStorage.removeItem(LEGACY_ACCESS_TOKEN_KEY)
  }
  return legacyToken
}

export function readRefreshToken(): string | null {
  const token = localStorage.getItem(REFRESH_TOKEN_KEY) || sessionStorage.getItem(REFRESH_TOKEN_KEY)
  if (token) return token
  const legacyToken = localStorage.getItem(LEGACY_REFRESH_TOKEN_KEY)
  if (legacyToken) {
    localStorage.setItem(REFRESH_TOKEN_KEY, legacyToken)
    localStorage.removeItem(LEGACY_REFRESH_TOKEN_KEY)
  }
  return legacyToken
}

export function persistTokens(accessToken: string, refreshToken: string, remember = true): void {
  const storage = remember ? localStorage : sessionStorage
  const otherStorage = remember ? sessionStorage : localStorage
  storage.setItem(ACCESS_TOKEN_KEY, accessToken)
  storage.setItem(REFRESH_TOKEN_KEY, refreshToken)
  otherStorage.removeItem(ACCESS_TOKEN_KEY)
  otherStorage.removeItem(REFRESH_TOKEN_KEY)
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
  localStorage.removeItem(LEGACY_ACCESS_TOKEN_KEY)
  localStorage.removeItem(LEGACY_REFRESH_TOKEN_KEY)
  sessionStorage.removeItem(ACCESS_TOKEN_KEY)
  sessionStorage.removeItem(REFRESH_TOKEN_KEY)
}

apiClient.interceptors.request.use((config) => {
  const token = readAccessToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

let refreshPromise: Promise<string> | null = null

export function isAuthenticationError(error: unknown): boolean {
  return axios.isAxiosError(error) && error.response?.status === 401
}

function expireSession(): void {
  const hadTokens = Boolean(readAccessToken() || readRefreshToken())
  clearTokens()
  if (hadTokens) window.dispatchEvent(new CustomEvent('contentpilot:session-expired'))
}

async function requestNewAccessToken(): Promise<string> {
  const refreshToken = readRefreshToken()
  if (!refreshToken) {
    expireSession()
    throw new AxiosError('No refresh token', 'ERR_SESSION_EXPIRED', undefined, undefined, {
      status: 401,
      statusText: 'Unauthorized',
      data: null,
      headers: {},
      config: { headers: new axios.AxiosHeaders() },
    })
  }

  try {
    const response = await axios.post<ApiResponse<AuthData>>(
      '/api/auth/refresh',
      { refresh_token: refreshToken },
      { timeout: REFRESH_TIMEOUT },
    )
    // An old in-flight refresh must not restore a session after sign-out or replace a new login.
    if (readRefreshToken() !== refreshToken) throw new Error('Session changed during refresh')
    const remember = Boolean(localStorage.getItem(REFRESH_TOKEN_KEY))
    persistTokens(response.data.data.access_token, response.data.data.refresh_token, remember)
    return response.data.data.access_token
  } catch (error) {
    if (
      (isAuthenticationError(error) ||
        (axios.isAxiosError(error) && error.response?.status === 403)) &&
      readRefreshToken() === refreshToken
    ) {
      expireSession()
    }
    throw error
  }
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiResponse<unknown>>) => {
    const original = error.config as RetryRequestConfig | undefined
    const requestPath = original?.url?.split('?')[0]?.replace(/\/$/, '')
    const cannotRefresh = ['/auth/login', '/auth/register', '/auth/refresh', '/auth/options'].some(
      (path) => requestPath?.endsWith(path),
    )

    if (
      error.response?.status === 401 &&
      original &&
      !cannotRefresh &&
      original._retry &&
      original.headers.Authorization === `Bearer ${readAccessToken()}`
    ) {
      expireSession()
    }
    if (error.response?.status === 401 && original && !original._retry && !cannotRefresh) {
      original._retry = true
      refreshPromise ??= requestNewAccessToken().finally(() => {
        refreshPromise = null
      })
      try {
        const token = await refreshPromise
        original.headers.Authorization = `Bearer ${token}`
        return apiClient(original)
      } catch (refreshError) {
        // Preserve the refresh failure: a 5xx/timeout is not evidence of an invalid session.
        return Promise.reject(refreshError)
      }
    }
    return Promise.reject(error)
  },
)

export function getApiErrorMessage(error: unknown, fallback = '请求失败，请稍后重试'): string {
  if (axios.isAxiosError<ApiResponse<unknown>>(error)) {
    if (error.response?.data?.message) {
      const message = error.response.data.message
      const looksTechnical =
        /\b(?:rid|request.?id|external_id|client_id|client_secret|access_token|refresh_token)\b|api unauthorized|\bexception\b|\btraceback\b|\bHTTP\s+[45]\d\d\b|[{}]|\b[a-z]+_[a-z_]+\b/i.test(
          message,
        )
      return looksTechnical ? fallback : message
    }
    if (error.code === 'ECONNABORTED') return '请求超时，请检查后端服务'
    if (!error.response) return '无法连接后端服务，请确认服务已启动'
  }
  return fallback
}
