import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useAuthStore } from '@/stores/auth'
import * as authApi from '@/api/auth'
import { AxiosError, AxiosHeaders } from 'axios'
import { persistTokens, readAccessToken, readRefreshToken } from '@/api/client'
import type { AuthData, User } from '@/types/user'

vi.mock('@/api/auth', () => ({
  login: vi.fn(),
  register: vi.fn(),
  fetchCurrentUser: vi.fn(),
  logout: vi.fn(),
  changePassword: vi.fn(),
}))

const user: User = {
  id: 2,
  username: 'operator',
  display_name: '内容运营者',
  email: null,
  avatar_url: null,
  status: 'ACTIVE',
  last_login_at: null,
  roles: [{ code: 'OPERATOR', name: '内容运营者' }],
}
const authData: AuthData = {
  access_token: 'access',
  refresh_token: 'refresh',
  token_type: 'bearer',
  expires_in: 7200,
  user,
}
function failure(status: number) {
  return new AxiosError('Failed', 'ERR_BAD_RESPONSE', undefined, undefined, {
    status,
    statusText: 'Failed',
    data: { message: 'Failed' },
    headers: {},
    config: { headers: new AxiosHeaders() },
  })
}

describe('auth store RBAC', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    sessionStorage.clear()
    vi.resetAllMocks()
  })

  it('matches only roles assigned to the current user', () => {
    const store = useAuthStore()
    store.user = {
      id: 2,
      username: 'operator',
      display_name: '内容运营者',
      email: null,
      avatar_url: null,
      status: 'ACTIVE',
      last_login_at: null,
      roles: [{ code: 'OPERATOR', name: '内容运营者' }],
    }

    expect(store.hasRole(['OPERATOR'])).toBe(true)
    expect(store.hasRole(['ADMIN'])).toBe(false)
  })

  it('stores login credentials in the selected storage', async () => {
    vi.mocked(authApi.login).mockResolvedValue(authData)
    const store = useAuthStore()
    await store.signIn({ username: 'operator', password: 'Content123' }, false)
    expect(store.isAuthenticated).toBe(true)
    expect(sessionStorage.getItem('contentpilot_refresh_token')).toBe('refresh')
    expect(localStorage.getItem('contentpilot_refresh_token')).toBeNull()
  })

  it.each([new AxiosError('Network Error'), failure(503)])(
    'preserves user and credentials when bootstrap fails transiently: %s',
    async (error) => {
      const store = useAuthStore()
      store.user = user
      persistTokens('access', 'refresh')
      vi.mocked(authApi.fetchCurrentUser).mockRejectedValueOnce(error).mockResolvedValueOnce(user)
      await store.bootstrap()
      expect(store.user).toEqual(user)
      expect(store.initialized).toBe(false)
      expect(store.connectionError).toBe(true)
      expect(readAccessToken()).toBe('access')
      expect(readRefreshToken()).toBe('refresh')
      await store.bootstrap()
      expect(store.initialized).toBe(true)
      expect(store.connectionError).toBe(false)
      expect(authApi.fetchCurrentUser).toHaveBeenCalledTimes(2)
    },
  )

  it('does not clear a refresh-only session on a transient bootstrap failure', async () => {
    sessionStorage.setItem('contentpilot_refresh_token', 'refresh')
    vi.mocked(authApi.fetchCurrentUser).mockRejectedValue(new AxiosError('Network Error'))
    const store = useAuthStore()
    await store.bootstrap()
    expect(readRefreshToken()).toBe('refresh')
    expect(store.initialized).toBe(false)
  })

  it('clears credentials after a definitive rejected session', async () => {
    persistTokens('access', 'refresh')
    vi.mocked(authApi.fetchCurrentUser).mockRejectedValue(failure(401))
    const store = useAuthStore()
    store.user = user
    await store.bootstrap()
    expect(store.user).toBeNull()
    expect(readAccessToken()).toBeNull()
    expect(readRefreshToken()).toBeNull()
  })

  it('keeps credentials if server logout fails so revocation can be retried', async () => {
    persistTokens('access', 'refresh')
    vi.mocked(authApi.logout).mockRejectedValue(failure(503))
    const store = useAuthStore()
    store.user = user
    await expect(store.signOut()).rejects.toThrow()
    expect(store.user).toEqual(user)
    expect(readRefreshToken()).toBe('refresh')
    vi.mocked(authApi.logout).mockResolvedValue(undefined)
    await store.signOut()
    expect(store.user).toBeNull()
    expect(readRefreshToken()).toBeNull()
  })

  it('requires a new login after a successful password change', async () => {
    persistTokens('access', 'refresh')
    vi.mocked(authApi.changePassword).mockResolvedValue(undefined)
    const store = useAuthStore()
    store.user = user
    await store.changePassword('Content123', 'Changed456')
    expect(authApi.changePassword).toHaveBeenCalledWith('Content123', 'Changed456')
    expect(store.user).toBeNull()
    expect(readAccessToken()).toBeNull()
    expect(readRefreshToken()).toBeNull()
  })

  it('keeps the session if changing the password fails', async () => {
    persistTokens('access', 'refresh')
    vi.mocked(authApi.changePassword).mockRejectedValue(failure(400))
    const store = useAuthStore()
    store.user = user
    await expect(store.changePassword('Wrong123', 'Changed456')).rejects.toThrow()
    expect(store.user).toEqual(user)
    expect(readAccessToken()).toBe('access')
  })

  it('does not let an old bootstrap failure clear a newer successful login', async () => {
    persistTokens('old-access', 'old-refresh')
    let rejectProfile!: (reason: unknown) => void
    vi.mocked(authApi.fetchCurrentUser).mockImplementation(
      () =>
        new Promise((_resolve, reject) => {
          rejectProfile = reject
        }),
    )
    const store = useAuthStore()
    const bootstrap = store.bootstrap()
    vi.mocked(authApi.login).mockResolvedValue(authData)
    await store.signIn({ username: 'operator', password: 'Content123' })
    rejectProfile(failure(401))
    await bootstrap
    expect(store.user).toEqual(user)
    expect(readAccessToken()).toBe('access')
    expect(readRefreshToken()).toBe('refresh')
  })
})
