import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import * as authApi from '@/api/auth'
import { clearTokens, persistTokens, readAccessToken } from '@/api/client'
import type { LoginPayload, RoleCode, User } from '@/types/user'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const initialized = ref(false)
  const loading = ref(false)

  const isAuthenticated = computed(() => Boolean(user.value && readAccessToken()))
  const roleCodes = computed(() => user.value?.roles.map((role) => role.code) ?? [])
  const primaryRoleName = computed(() => user.value?.roles[0]?.name ?? '未分配角色')

  function hasRole(roles: RoleCode[]): boolean {
    return roles.some((role) => roleCodes.value.includes(role))
  }

  async function signIn(payload: LoginPayload): Promise<void> {
    loading.value = true
    try {
      const data = await authApi.login(payload)
      persistTokens(data.access_token, data.refresh_token)
      user.value = data.user
    } finally {
      loading.value = false
      initialized.value = true
    }
  }

  async function bootstrap(): Promise<void> {
    if (initialized.value) return
    if (!readAccessToken()) {
      initialized.value = true
      return
    }
    try {
      user.value = await authApi.fetchCurrentUser()
    } catch {
      clearTokens()
      user.value = null
    } finally {
      initialized.value = true
    }
  }

  async function signOut(): Promise<void> {
    try {
      if (readAccessToken()) await authApi.logout()
    } finally {
      clearTokens()
      user.value = null
      initialized.value = true
    }
  }

  function clearSession(): void {
    clearTokens()
    user.value = null
    initialized.value = true
  }

  return {
    user,
    initialized,
    loading,
    isAuthenticated,
    roleCodes,
    primaryRoleName,
    hasRole,
    signIn,
    bootstrap,
    signOut,
    clearSession,
  }
})
