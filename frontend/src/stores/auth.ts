import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import * as authApi from '@/api/auth'
import {
  clearTokens,
  isAuthenticationError,
  persistTokens,
  readAccessToken,
  readRefreshToken,
} from '@/api/client'
import type { LoginPayload, RegisterPayload, RoleCode, User } from '@/types/user'
import {
  ROLE_SCOPES,
  canManageBusiness as checkCanManageBusiness,
  canManageSystem as checkCanManageSystem,
  isViewerOnly as checkIsViewerOnly,
  isSystemAdminOnly as checkIsSystemAdminOnly,
  pickPrimaryRole,
} from '@/config/roles'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const initialized = ref(false)
  const loading = ref(false)
  const connectionError = ref(false)
  let bootstrapPromise: Promise<void> | null = null
  let sessionGeneration = 0

  const isAuthenticated = computed(() => Boolean(user.value && readAccessToken()))
  const roleCodes = computed(() => user.value?.roles.map((role) => role.code) ?? [])
  const primaryRoleCode = computed(() => pickPrimaryRole(roleCodes.value))
  const primaryRoleName = computed(
    () =>
      (primaryRoleCode.value && ROLE_SCOPES[primaryRoleCode.value]?.label) ||
      user.value?.roles[0]?.name ||
      '未分配角色',
  )
  const canManageSystem = computed(() => checkCanManageSystem(roleCodes.value))
  const canManageBusiness = computed(() => checkCanManageBusiness(roleCodes.value))
  const isViewerOnly = computed(() => checkIsViewerOnly(roleCodes.value))
  const isSystemAdminOnly = computed(() => checkIsSystemAdminOnly(roleCodes.value))

  function hasRole(roles: RoleCode[]): boolean {
    return roles.some((role) => roleCodes.value.includes(role))
  }

  async function signIn(payload: LoginPayload, remember = true): Promise<void> {
    loading.value = true
    try {
      const data = await authApi.login(payload)
      persistTokens(data.access_token, data.refresh_token, remember)
      user.value = data.user
      sessionGeneration += 1
      initialized.value = true
      connectionError.value = false
    } finally {
      loading.value = false
    }
  }

  async function signUp(payload: RegisterPayload, remember = true): Promise<void> {
    loading.value = true
    try {
      const data = await authApi.register(payload)
      persistTokens(data.access_token, data.refresh_token, remember)
      user.value = data.user
      sessionGeneration += 1
      initialized.value = true
      connectionError.value = false
    } finally {
      loading.value = false
    }
  }

  async function bootstrap(): Promise<void> {
    if (initialized.value) return
    if (!readAccessToken() && !readRefreshToken()) {
      initialized.value = true
      return
    }
    const generation = sessionGeneration
    bootstrapPromise ??= (async () => {
      try {
        const profile = await authApi.fetchCurrentUser()
        if (generation === sessionGeneration) {
          user.value = profile
          initialized.value = true
          connectionError.value = false
        }
      } catch (error) {
        if (
          generation === sessionGeneration &&
          (isAuthenticationError(error) || (!readAccessToken() && !readRefreshToken()))
        ) {
          clearSession()
        } else if (generation === sessionGeneration) {
          connectionError.value = true
        }
        // Keep both the current user and credentials on transient failures; the next
        // navigation can retry bootstrap instead of permanently marking it completed.
      }
    })().finally(() => {
      bootstrapPromise = null
    })
    await bootstrapPromise
  }

  async function signOut(): Promise<void> {
    try {
      if (readAccessToken() || readRefreshToken()) await authApi.logout()
    } catch (error) {
      if (!isAuthenticationError(error)) throw error
    }
    clearSession()
  }

  async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
    await authApi.changePassword(currentPassword, newPassword)
    clearSession()
  }

  function clearSession(): void {
    sessionGeneration += 1
    clearTokens()
    user.value = null
    initialized.value = true
    connectionError.value = false
  }

  return {
    user,
    initialized,
    loading,
    connectionError,
    isAuthenticated,
    roleCodes,
    primaryRoleCode,
    primaryRoleName,
    canManageSystem,
    canManageBusiness,
    isViewerOnly,
    isSystemAdminOnly,
    hasRole,
    signIn,
    signUp,
    bootstrap,
    signOut,
    changePassword,
    clearSession,
  }
})
