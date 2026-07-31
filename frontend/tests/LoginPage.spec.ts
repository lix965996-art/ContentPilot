import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import { fireEvent, render, screen, waitFor } from '@testing-library/vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'

import LoginPage from '@/pages/LoginPage.vue'

vi.mock('@/api/auth', () => ({
  login: vi.fn().mockResolvedValue({
    access_token: 'access-token',
    refresh_token: 'refresh-token',
    token_type: 'bearer',
    expires_in: 7200,
    user: {
      id: 1,
      username: 'admin',
      display_name: '系统管理员',
      email: 'admin@contentpilot.local',
      avatar_url: null,
      status: 'ACTIVE',
      last_login_at: null,
      roles: [{ code: 'ADMIN', name: '管理员' }],
    },
  }),
  register: vi.fn().mockResolvedValue({
    access_token: 'registered-access-token',
    refresh_token: 'registered-refresh-token',
    token_type: 'bearer',
    expires_in: 7200,
    user: {
      id: 9,
      username: 'new_operator',
      display_name: '新运营者',
      email: 'new@example.com',
      avatar_url: null,
      status: 'ACTIVE',
      last_login_at: null,
      roles: [{ code: 'OPERATOR', name: '运营者' }],
    },
  }),
  fetchCurrentUser: vi.fn(),
  logout: vi.fn(),
}))

async function renderPage() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/login', name: 'login', component: LoginPage },
      { path: '/register', name: 'register', component: LoginPage },
      { path: '/', component: { template: '<div>工作台</div>' } },
    ],
  })
  await router.push('/login')
  await router.isReady()

  render(LoginPage, {
    global: { plugins: [createPinia(), router, ElementPlus] },
  })
  return router
}

describe('LoginPage', () => {
  it('fills a demo account and logs in', async () => {
    const router = await renderPage()

    await fireEvent.click(screen.getByTestId('demo-admin'))
    const usernameInput = screen.getByTestId('username-input') as HTMLInputElement
    const passwordInput = screen.getByTestId('password-input') as HTMLInputElement
    expect(usernameInput.value).toBe('admin')
    expect(passwordInput.value).toBe('Admin@123456')

    await fireEvent.click(screen.getByTestId('login-button'))

    await waitFor(() => expect(router.currentRoute.value.path).toBe('/'))
    expect(localStorage.getItem('contentpilot_access_token')).toBe('access-token')
  })

  it('shows all three demo roles', async () => {
    await renderPage()

    expect(screen.getByText('管理员')).toBeTruthy()
    expect(screen.getByText('运营者')).toBeTruthy()
    expect(screen.getByText('查看者')).toBeTruthy()
  })

  it('registers a new operator and enters the workspace', async () => {
    const router = await renderPage()
    await fireEvent.click(screen.getByTestId('auth-mode-switch'))
    await waitFor(() => expect(router.currentRoute.value.path).toBe('/register'))

    await fireEvent.update(screen.getByTestId('display-name-input'), '新运营者')
    await fireEvent.update(screen.getByTestId('username-input'), 'new_operator')
    await fireEvent.update(screen.getByTestId('email-input'), 'new@example.com')
    await fireEvent.update(screen.getByTestId('password-input'), 'Content123')
    expect(screen.getByTestId('password-strength').textContent).toContain('符合要求')
    await fireEvent.update(screen.getByTestId('confirm-password-input'), 'Content123')
    await fireEvent.click(screen.getByTestId('register-button'))

    await waitFor(() => expect(router.currentRoute.value.path).toBe('/'))
    expect(localStorage.getItem('contentpilot_access_token')).toBe('registered-access-token')
  })
})
