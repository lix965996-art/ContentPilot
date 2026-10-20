import { fireEvent, render, screen, waitFor, within } from '@testing-library/vue'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PlatformAccountsPage from '@/pages/PlatformAccountsPage.vue'
import { workflowApi } from '@/api/workflow'
import type { PlatformAccount } from '@/types/business'

const routeState = vi.hoisted(() => ({ query: {} as Record<string, string> }))
vi.mock('vue-router', () => ({
  useRoute: () => routeState,
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
  platform: 'MASTODON',
  platformName: 'Mastodon',
  accountName: '毕业设计账号',
  authType: 'ACCESS_TOKEN',
  publishMode: 'REAL_API',
  status: 'CONNECTED',
  capabilities: ['TEXT_PUBLISH', 'IMAGE_PUBLISH'],
  publishHint: '连接测试不会发送帖子',
  appId: '',
  clientId: '',
  secretConfigured: false,
  accessTokenConfigured: true,
  instanceUrl: 'https://mastodon.social',
  refreshTokenConfigured: false,
  tokenHint: '',
  localPublishingEnabled: false,
  publicPublishEnabled: false,
  availablePublishModes: ['REAL_API'],
  config: { instanceUrl: 'https://mastodon.social', allow_public_publish: false },
  connectionGuide: {
    mode: 'ACCESS_TOKEN',
    consoleUrl: 'https://mastodon.social/settings/applications',
    steps: [],
  },
}

beforeEach(() => {
  vi.clearAllMocks()
  routeState.query = {}
  vi.mocked(workflowApi.platformAccounts).mockResolvedValue([account])
  vi.mocked(workflowApi.savePlatformAccount).mockResolvedValue(account)
  vi.mocked(workflowApi.testPlatformAccount).mockResolvedValue({
    ...account,
    result: { success: true, error_message: '', suggested_action: '', error_code: '' },
  })
})

async function openEditor() {
  render(PlatformAccountsPage, { global: { plugins: [ElementPlus] } })
  const card = await screen.findByTestId('platform-account-MASTODON')
  await fireEvent.click(within(card).getByRole('button', { name: '编辑配置' }))
  await screen.findByTestId('mastodon-access-token')
  return card
}

describe('Mastodon account configuration', () => {
  it('opens the Mastodon editor from the platform setup link', async () => {
    routeState.query.platform = 'MASTODON'
    render(PlatformAccountsPage, { global: { plugins: [ElementPlus] } })
    const server = (await screen.findByTestId('mastodon-instance-url')) as HTMLInputElement
    expect(server.value).toBe('https://mastodon.social')
    expect(workflowApi.savePlatformAccount).not.toHaveBeenCalled()
  })

  it('requires a server origin and an access token for first-time setup', async () => {
    vi.mocked(workflowApi.platformAccounts).mockResolvedValue([
      { ...account, accessTokenConfigured: false, status: 'NOT_CONFIGURED' },
    ])
    await openEditor()
    await fireEvent.click(screen.getByTestId('save-platform-account'))
    expect(workflowApi.savePlatformAccount).not.toHaveBeenCalled()
    await fireEvent.update(screen.getByTestId('mastodon-access-token'), 'example-access-token')
    await fireEvent.update(screen.getByTestId('mastodon-instance-url'), 'http://mastodon.social')
    await fireEvent.click(screen.getByTestId('save-platform-account'))
    expect(workflowApi.savePlatformAccount).not.toHaveBeenCalled()
    await fireEvent.update(
      screen.getByTestId('mastodon-instance-url'),
      'https://mastodon.social/@student',
    )
    await fireEvent.click(screen.getByTestId('save-platform-account'))
    expect(workflowApi.savePlatformAccount).not.toHaveBeenCalled()
  })

  it('keeps saved access tokens write-only and omits a blank replacement', async () => {
    await openEditor()
    const password = screen.getByTestId('mastodon-access-token') as HTMLInputElement
    expect(password.type).toBe('password')
    expect(password.value).toBe('')
    expect((screen.getByTestId('mastodon-instance-url') as HTMLInputElement).value).toBe(
      'https://mastodon.social',
    )
    await fireEvent.click(screen.getByTestId('save-platform-account'))
    await waitFor(() => expect(workflowApi.savePlatformAccount).toHaveBeenCalledTimes(1))
    const [platform, payload] = vi.mocked(workflowApi.savePlatformAccount).mock.calls[0]!
    expect(platform).toBe('MASTODON')
    expect(payload.instance_url).toBe('https://mastodon.social')
    expect(payload).not.toHaveProperty('access_token')
    expect(payload.allow_public_publish).toBe(false)
  })

  it('tests account connectivity without issuing any publish request', async () => {
    render(PlatformAccountsPage, { global: { plugins: [ElementPlus] } })
    const card = await screen.findByTestId('platform-account-MASTODON')
    await fireEvent.click(within(card).getByRole('button', { name: '验证真实连接' }))
    await waitFor(() => expect(workflowApi.testPlatformAccount).toHaveBeenCalledWith('MASTODON'))
    expect(workflowApi.savePlatformAccount).not.toHaveBeenCalled()
  })

  it('saves a replacement token once and clears it from subsequent edits', async () => {
    const card = await openEditor()
    const password = screen.getByTestId('mastodon-access-token') as HTMLInputElement
    await fireEvent.update(password, 'example-access-token')
    await fireEvent.click(screen.getByTestId('save-platform-account'))
    await waitFor(() => expect(workflowApi.savePlatformAccount).toHaveBeenCalledTimes(1))
    expect(vi.mocked(workflowApi.savePlatformAccount).mock.calls[0]?.[1].access_token).toBe(
      'example-access-token',
    )
    await waitFor(() => expect(password.value).toBe(''))
    await fireEvent.click(within(card).getByRole('button', { name: '编辑配置' }))
    expect(((await screen.findByTestId('mastodon-access-token')) as HTMLInputElement).value).toBe(
      '',
    )
  })
})
