import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import * as authApi from '@/api/auth'
import { apiClient, persistTokens, readAccessToken, readRefreshToken } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import type { AuthData, User } from '@/types/user'

const user: User = {
  id: 2,
  username: 'operator',
  display_name: '运营者',
  email: null,
  avatar_url: null,
  status: 'ACTIVE',
  last_login_at: null,
  roles: [{ code: 'OPERATOR', name: '运营者' }],
}
const renewed: AuthData = {
  access_token: 'renewed-access',
  refresh_token: 'renewed-refresh',
  token_type: 'bearer',
  expires_in: 7200,
  user,
}
const originalAdapter = apiClient.defaults.adapter
const sessionExpired = vi.fn()

function response(config: InternalAxiosRequestConfig, data: unknown, status = 200) {
  return { config, data, status, statusText: 'OK', headers: {} }
}
function rejectResponse(config: InternalAxiosRequestConfig, status: number): never {
  throw new AxiosError(
    `HTTP ${status}`,
    'ERR_BAD_RESPONSE',
    config,
    undefined,
    response(config, { code: status, data: null, message: '请求失败' }, status),
  )
}
function authenticatedAdapter(config: InternalAxiosRequestConfig) {
  if (config.headers.get('Authorization') !== 'Bearer renewed-access') rejectResponse(config, 401)
  return Promise.resolve(response(config, { code: 0, data: user, message: '成功' }))
}
function renewedResponse() {
  return { data: { code: 0, data: renewed, message: '已续期' } }
}

describe('auth API refresh and session lifecycle', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    sessionStorage.clear()
    sessionExpired.mockClear()
    window.addEventListener('contentpilot:session-expired', sessionExpired)
    persistTokens('expired-access', 'old-refresh')
  })
  afterEach(() => {
    apiClient.defaults.adapter = originalAdapter
    window.removeEventListener('contentpilot:session-expired', sessionExpired)
    vi.restoreAllMocks()
  })

  it('renews an expired /auth/me during store bootstrap with a bounded refresh timeout', async () => {
    apiClient.defaults.adapter = authenticatedAdapter
    const refresh = vi.spyOn(axios, 'post').mockResolvedValue(renewedResponse())
    const store = useAuthStore()
    await store.bootstrap()
    expect(store.user).toEqual(user)
    expect(store.isAuthenticated).toBe(true)
    expect(refresh).toHaveBeenCalledExactlyOnceWith(
      '/api/auth/refresh',
      { refresh_token: 'old-refresh' },
      { timeout: 15_000 },
    )
    expect(readAccessToken()).toBe('renewed-access')
    expect(sessionExpired).not.toHaveBeenCalled()
  })

  it('shares one refresh between concurrent expired requests', async () => {
    apiClient.defaults.adapter = authenticatedAdapter
    const refresh = vi.spyOn(axios, 'post').mockResolvedValue(renewedResponse())
    const [first, second] = await Promise.all([
      authApi.fetchCurrentUser(),
      apiClient.get('/articles'),
    ])
    expect(first).toEqual(user)
    expect(second.status).toBe(200)
    expect(refresh).toHaveBeenCalledTimes(1)
  })

  it.each(['/auth/login', '/auth/register', '/auth/refresh'])(
    'does not recursively refresh %s or erase the existing session',
    async (path) => {
      apiClient.defaults.adapter = async (config) => rejectResponse(config, 401)
      const refresh = vi.spyOn(axios, 'post')
      await expect(apiClient.post(path, {})).rejects.toMatchObject({ response: { status: 401 } })
      expect(refresh).not.toHaveBeenCalled()
      expect(readAccessToken()).toBe('expired-access')
      expect(readRefreshToken()).toBe('old-refresh')
    },
  )

  it.each([
    new AxiosError('Network Error', 'ERR_NETWORK'),
    new AxiosError('Timeout', 'ECONNABORTED'),
    new AxiosError('Unavailable', 'ERR_BAD_RESPONSE', undefined, undefined, {
      status: 503,
      statusText: 'Unavailable',
      data: {},
      headers: {},
      config: { headers: new axios.AxiosHeaders() },
    }),
  ])(
    'preserves credentials and retries bootstrap after transient refresh failure: %s',
    async (error) => {
      apiClient.defaults.adapter = authenticatedAdapter
      const refresh = vi
        .spyOn(axios, 'post')
        .mockRejectedValueOnce(error)
        .mockResolvedValueOnce(renewedResponse())
      const store = useAuthStore()
      store.user = user
      await store.bootstrap()
      expect(store.user).toEqual(user)
      expect(store.initialized).toBe(false)
      expect(readAccessToken()).toBe('expired-access')
      expect(readRefreshToken()).toBe('old-refresh')
      expect(sessionExpired).not.toHaveBeenCalled()
      await store.bootstrap()
      expect(store.initialized).toBe(true)
      expect(readAccessToken()).toBe('renewed-access')
      expect(refresh).toHaveBeenCalledTimes(2)
    },
  )

  it('does not erase the current session for an ordinary API server error', async () => {
    apiClient.defaults.adapter = async (config) => rejectResponse(config, 503)
    const refresh = vi.spyOn(axios, 'post')
    const store = useAuthStore()
    store.user = user
    await store.bootstrap()
    expect(store.user).toEqual(user)
    expect(readRefreshToken()).toBe('old-refresh')
    expect(refresh).not.toHaveBeenCalled()
    expect(sessionExpired).not.toHaveBeenCalled()
  })

  it('clears rejected refresh credentials and emits one expiry event for concurrent requests', async () => {
    apiClient.defaults.adapter = authenticatedAdapter
    const refresh = vi.spyOn(axios, 'post').mockImplementation(async (_url, _payload, config) => {
      rejectResponse(
        { ...config, headers: new axios.AxiosHeaders() } as InternalAxiosRequestConfig,
        401,
      )
    })
    const results = await Promise.allSettled([
      authApi.fetchCurrentUser(),
      apiClient.get('/articles'),
    ])
    expect(results.every((result) => result.status === 'rejected')).toBe(true)
    expect(refresh).toHaveBeenCalledTimes(1)
    expect(readAccessToken()).toBeNull()
    expect(readRefreshToken()).toBeNull()
    expect(sessionExpired).toHaveBeenCalledTimes(1)
  })

  it('stops after one refresh if the renewed access token is also rejected', async () => {
    apiClient.defaults.adapter = async (config) => rejectResponse(config, 401)
    const refresh = vi.spyOn(axios, 'post').mockResolvedValue(renewedResponse())
    await expect(authApi.fetchCurrentUser()).rejects.toMatchObject({ response: { status: 401 } })
    expect(refresh).toHaveBeenCalledTimes(1)
    expect(readRefreshToken()).toBeNull()
    expect(sessionExpired).toHaveBeenCalledTimes(1)
  })

  it('preserves session storage when renewing a non-remembered login', async () => {
    persistTokens('expired-access', 'old-refresh', false)
    apiClient.defaults.adapter = authenticatedAdapter
    vi.spyOn(axios, 'post').mockResolvedValue(renewedResponse())
    await authApi.fetchCurrentUser()
    expect(sessionStorage.getItem('contentpilot_refresh_token')).toBe('renewed-refresh')
    expect(localStorage.getItem('contentpilot_refresh_token')).toBeNull()
  })

  it('does not overwrite a newer login when an older refresh completes late', async () => {
    apiClient.defaults.adapter = authenticatedAdapter
    let finishRefresh!: (value: ReturnType<typeof renewedResponse>) => void
    const refresh = vi.spyOn(axios, 'post').mockImplementation(
      () =>
        new Promise((resolve) => {
          finishRefresh = resolve
        }),
    )
    const request = authApi.fetchCurrentUser()
    await vi.waitFor(() => expect(refresh).toHaveBeenCalledTimes(1))
    persistTokens('different-access', 'different-refresh')
    finishRefresh(renewedResponse())
    await expect(request).rejects.toThrow('Session changed')
    expect(readAccessToken()).toBe('different-access')
    expect(readRefreshToken()).toBe('different-refresh')
    expect(sessionExpired).not.toHaveBeenCalled()
  })

  it('submits the password fields and clears the store only after server success', async () => {
    let submitted: unknown
    apiClient.defaults.adapter = async (config) => {
      expect(config.url).toBe('/auth/password')
      expect(config.method).toBe('put')
      submitted = JSON.parse(config.data)
      return response(config, { code: 0, data: null, message: '请重新登录' })
    }
    const store = useAuthStore()
    store.user = user
    await store.changePassword('Content123', 'Changed456')
    expect(submitted).toEqual({ current_password: 'Content123', new_password: 'Changed456' })
    expect(store.user).toBeNull()
    expect(readRefreshToken()).toBeNull()
  })
})
