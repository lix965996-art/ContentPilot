import { fireEvent, render, screen, waitFor, within } from '@testing-library/vue'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PlatformAccountsPage from '@/pages/PlatformAccountsPage.vue'
import { workflowApi } from '@/api/workflow'
import type { PlatformAccount } from '@/types/business'

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ replace: vi.fn() }),
}))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ canManageSystem: true }) }))
vi.mock('@/api/workflow', () => ({
  workflowApi: {
    platformAccounts: vi.fn(),
    savePlatformAccount: vi.fn(),
    testPlatformAccount: vi.fn(),
  },
}))

const account: PlatformAccount = {
  id: 10,
  platform: 'BLUESKY',
  platformName: 'Bluesky',
  accountName: '毕业设计账号',
  authType: 'APP_PASSWORD',
  publishMode: 'REAL_API',
  status: 'CONNECTED',
  capabilities: ['TEXT_PUBLISH', 'IMAGE_PUBLISH'],
  publishHint: '连接测试不会发送帖子',
  appId: '',
  clientId: '',
  secretConfigured: false,
  appPasswordConfigured: true,
  accessTokenConfigured: false,
  refreshTokenConfigured: false,
  tokenHint: '',
  localPublishingEnabled: false,
  publicPublishEnabled: false,
  availablePublishModes: ['REAL_API'],
  config: { identifier: 'student.bsky.social', allow_public_publish: false },
  connectionGuide: {
    mode: 'APP_PASSWORD',
    consoleUrl: 'https://bsky.app/settings/app-passwords',
    steps: [],
  },
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(workflowApi.platformAccounts).mockResolvedValue([account])
  vi.mocked(workflowApi.savePlatformAccount).mockResolvedValue(account)
  vi.mocked(workflowApi.testPlatformAccount).mockResolvedValue({
    ...account,
    result: { success: true, error_message: '', suggested_action: '', error_code: '' },
  })
})

async function openEditor() {
  render(PlatformAccountsPage, { global: { plugins: [ElementPlus] } })
  const card = await screen.findByTestId('platform-account-BLUESKY')
  await fireEvent.click(within(card).getByRole('button', { name: '编辑配置' }))
  await screen.findByTestId('bluesky-app-password')
  return card
}

describe('Bluesky account configuration', () => {
  it('keeps saved application passwords write-only and omits a blank replacement', async () => {
    await openEditor()
    const password = screen.getByTestId('bluesky-app-password') as HTMLInputElement
    expect(password.type).toBe('password')
    expect(password.value).toBe('')
    expect((screen.getByTestId('bluesky-identifier') as HTMLInputElement).value).toBe(
      'student.bsky.social',
    )
    await fireEvent.click(screen.getByTestId('save-platform-account'))
    await waitFor(() => expect(workflowApi.savePlatformAccount).toHaveBeenCalledTimes(1))
    const [platform, payload] = vi.mocked(workflowApi.savePlatformAccount).mock.calls[0]!
    expect(platform).toBe('BLUESKY')
    expect(payload.identifier).toBe('student.bsky.social')
    expect(payload).not.toHaveProperty('app_password')
    expect(payload.allow_public_publish).toBe(false)
  })

  it('tests account connectivity without issuing any publish request', async () => {
    render(PlatformAccountsPage, { global: { plugins: [ElementPlus] } })
    const card = await screen.findByTestId('platform-account-BLUESKY')
    await fireEvent.click(within(card).getByRole('button', { name: '验证真实连接' }))
    await waitFor(() => expect(workflowApi.testPlatformAccount).toHaveBeenCalledWith('BLUESKY'))
    expect(workflowApi.savePlatformAccount).not.toHaveBeenCalled()
  })

  it('saves a replacement password once and clears it from subsequent edits', async () => {
    const card = await openEditor()
    const password = screen.getByTestId('bluesky-app-password') as HTMLInputElement
    await fireEvent.update(password, 'example-app-password')
    await fireEvent.click(screen.getByTestId('save-platform-account'))
    await waitFor(() => expect(workflowApi.savePlatformAccount).toHaveBeenCalledTimes(1))
    expect(vi.mocked(workflowApi.savePlatformAccount).mock.calls[0]?.[1].app_password).toBe(
      'example-app-password',
    )
    await waitFor(() => expect(password.value).toBe(''))
    await fireEvent.click(within(card).getByRole('button', { name: '编辑配置' }))
    expect(((await screen.findByTestId('bluesky-app-password')) as HTMLInputElement).value).toBe('')
  })
})
