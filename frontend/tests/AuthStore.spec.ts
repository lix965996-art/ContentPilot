import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useAuthStore } from '@/stores/auth'

vi.mock('@/api/auth', () => ({
  login: vi.fn(),
  fetchCurrentUser: vi.fn(),
  logout: vi.fn(),
}))

describe('auth store RBAC', () => {
  beforeEach(() => setActivePinia(createPinia()))

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
})
