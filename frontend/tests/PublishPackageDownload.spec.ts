import { beforeEach, expect, it, vi } from 'vitest'
import { AxiosError } from 'axios'
import { workflowApi } from '@/api/workflow'
import { getApiErrorMessage } from '@/api/client'

const mocks = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return { ...actual, apiClient: { get: mocks.get } }
})

beforeEach(() => {
  vi.clearAllMocks()
})

it('turns a JSON Blob failure into a visible missing-image message without downloading a ZIP', async () => {
  const message = '第 1 张图片无法完整打包，请检查图片后重试；未生成缺图发布包'
  const body = new Blob([], { type: 'application/json' })
  Object.defineProperty(body, 'text', {
    value: async () => JSON.stringify({ code: 50223, data: null, message }),
  })
  const error = new AxiosError('Request failed', 'ERR_BAD_RESPONSE')
  error.response = {
    data: body,
    status: 502,
    statusText: 'Bad Gateway',
    headers: {},
    config: { headers: {} },
  } as AxiosError['response']
  mocks.get.mockRejectedValueOnce(error)
  await expect(workflowApi.downloadPublishPackage(1)).rejects.toBe(error)
  expect(getApiErrorMessage(error)).toBe(message)
})
