<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  CheckCircle2,
  Link2,
  QrCode,
  RefreshCw,
  Settings2,
  ShieldAlert,
  Unlink,
} from 'lucide-vue-next'
import PageHeader from '@/components/PageHeader.vue'
import PlatformIcon from '@/components/PlatformIcon.vue'
import { workflowApi } from '@/api/workflow'
import { getApiErrorMessage } from '@/api/client'
import type { Platform, PlatformAccount } from '@/types/business'
import { useAuthStore } from '@/stores/auth'
import { presentOperationError } from '@/utils/operation-error'

const accounts = ref<PlatformAccount[]>([])
const auth = useAuthStore()
const isAdmin = computed(() => auth.hasRole(['ADMIN']))
const route = useRoute()
const router = useRouter()
const loading = ref(false)
const testing = ref<Platform | ''>('')
const drawer = ref(false)
const logDrawer = ref(false)
const qrDialog = ref(false)
const qrLoading = ref(false)
const qrImage = ref('')
const qrMessage = ref('')
const qrPolling = ref(false)
const qrPlatform = ref<'XIAOHONGSHU' | 'TOUTIAO' | 'WECHAT_OFFICIAL'>('XIAOHONGSHU')
const sessionClock = ref(Date.now())
const logs = ref<Array<Record<string, unknown>>>([])
const current = ref<PlatformAccount>()
let qrPollTimer: number | undefined
let sessionClockTimer: number | undefined

function accountErrorMessage(account: PlatformAccount) {
  const raw = account.lastError || ''
  const looksTechnical =
    /\b(?:rid|request.?id|external_id|default_cover_media_id|client_id|client_secret|access_token|refresh_token)\b|api unauthorized|\b(?:exception|traceback)\b|\bHTTP\s+[45]\d\d\b|\[\d{4,}\]|https?:\/\/|[{}]/i.test(
      raw,
    )
  if (!looksTechnical) return raw
  const issue = presentOperationError(raw, {
    type: 'PUBLISH',
    platform: account.platform,
  })
  return issue ? `${issue.title}：${issue.description}` : '平台连接异常，请重新验证账号连接。'
}

const form = reactive({
  account_name: '',
  auth_type: 'NONE',
  publish_mode: 'REAL_API',
  app_id: '',
  client_id: '',
  app_secret: '',
  access_token: '',
  refresh_token: '',
  token_expires_at: '',
  redirect_uri: '',
  operation_ip: '',
  default_author: '',
  default_cover_media_id: '',
  default_cover_url: '',
  allow_submit_publish: false,
  allow_public_publish: false,
  enabled: true,
})

const capabilityNames: Record<string, string> = {
  TEXT_PUBLISH: '文字发布',
  IMAGE_PUBLISH: '图片发布',
  STATUS_READ: '数据读取',
  MATERIAL_UPLOAD: '素材上传',
  DRAFT_CREATE: '草稿创建',
  SUBMIT_PUBLISH: '提交发布',
  COPYWRITING: '文案生成',
  IMAGE_PACKAGE: '图片打包',
  MANUAL_CONFIRM: '人工确认',
  ARTICLE_PUBLISH: '文章发布',
}
const statusNames: Record<string, string> = {
  NOT_CONFIGURED: '未配置',
  CONNECTING: '待检测',
  CONNECTED: '已连接',
  TOKEN_EXPIRED: 'Token 已过期',
  INVALID: '连接无效',
  DISABLED: '已停用',
  MANUAL_ONLY: '仅人工交付',
  READY: '已就绪',
  LOGIN_REQUIRED: '需要登录',
}
const statusType = (status: string) =>
  status === 'CONNECTED' || status === 'READY'
    ? 'success'
    : ['CONNECTING', 'MANUAL_ONLY'].includes(status)
      ? 'warning'
      : 'danger'
const title = computed(() => current.value?.platformName || '平台配置')
const xOAuthCredentialsReady = computed(
  () =>
    current.value?.platform !== 'X' ||
    Boolean(form.client_id.trim() && (form.app_secret.trim() || current.value?.secretConfigured)),
)
const publishModeNames: Record<string, string> = {
  REAL_API: '官方 API',
  DRAFT_ONLY: '真实草稿箱 (API)',
  SUBMIT_PUBLISH: '真实提交发布',
  MANUAL_CONFIRM: '人工发布交付',
  CDP_PUBLISH: 'Chrome 自动发布',
  WECHATSYNC_CLI: 'Wechatsync CLI',
  MCP_PUBLISH: '本机自动发布（仅自己可见）',
  BROWSER_PUBLISH: '本机浏览器发布',
  BROWSER_DRAFT: '本机扫码保存草稿',
}
function publishModeLabel(account: PlatformAccount): string {
  if (account.publishMode === 'REAL_API' && account.platform === 'WEIBO') return '微博官方 API'
  if (account.publishMode === 'REAL_API' && account.platform === 'X') return 'X 官方 API'
  return publishModeNames[account.publishMode] || account.publishMode
}

function formatDateTime(value?: string): string {
  return value ? new Date(value).toLocaleString('zh-CN') : '尚未记录'
}

function loginDuration(account: PlatformAccount): string {
  if (account.status !== 'CONNECTED' || !account.lastLoginAt) return '当前未登录'
  const startedAt = new Date(account.lastLoginAt).getTime()
  if (!Number.isFinite(startedAt)) return '时间未知'
  const totalMinutes = Math.max(0, Math.floor((sessionClock.value - startedAt) / 60_000))
  if (totalMinutes < 1) return '不足 1 分钟'
  const days = Math.floor(totalMinutes / 1440)
  const hours = Math.floor((totalMinutes % 1440) / 60)
  const minutes = totalMinutes % 60
  return [
    days ? `${days} 天` : '',
    hours ? `${hours} 小时` : '',
    minutes || (!days && !hours) ? `${minutes} 分钟` : '',
  ]
    .filter(Boolean)
    .join(' ')
}

async function load() {
  loading.value = true
  try {
    accounts.value = await workflowApi.platformAccounts()
  } finally {
    loading.value = false
  }
}

function edit(account: PlatformAccount) {
  current.value = account
  Object.assign(form, {
    account_name:
      account.accountName === '未配置'
        ? account.platform === 'XIAOHONGSHU'
          ? 'ContentPilot 小红书'
          : account.platform === 'TOUTIAO'
            ? 'ContentPilot 今日头条'
            : account.platform === 'WECHAT_OFFICIAL'
              ? 'ContentPilot 公众号'
              : account.platform === 'X'
                ? 'ContentPilot X'
                : ''
        : account.accountName,
    auth_type:
      account.platform === 'WEIBO' || account.platform === 'X'
        ? 'OAUTH2'
        : account.platform === 'TOUTIAO'
          ? 'QR_LOGIN'
          : account.platform === 'WECHAT_OFFICIAL'
            ? account.publishMode === 'BROWSER_DRAFT'
              ? 'QR_LOGIN'
              : 'APP_SECRET'
            : 'NONE',
    publish_mode:
      account.platform === 'TOUTIAO'
        ? 'BROWSER_PUBLISH'
        : account.platform === 'XIAOHONGSHU'
          ? account.availablePublishModes.includes(account.publishMode)
            ? account.publishMode
            : 'MANUAL_CONFIRM'
          : account.platform === 'WECHAT_OFFICIAL'
            ? account.publishMode || 'DRAFT_ONLY'
            : 'REAL_API',
    app_id: account.appId,
    client_id: account.clientId,
    app_secret: '',
    access_token: '',
    refresh_token: '',
    token_expires_at: account.tokenExpiresAt?.slice(0, 16) || '',
    redirect_uri:
      account.config.redirect_uri ||
      (['X', 'WEIBO'].includes(account.platform)
        ? `http://127.0.0.1:8000/api/platform-accounts/${
            account.platform === 'X' ? 'X' : 'WEIBO'
          }/oauth/callback`
        : ''),
    operation_ip: account.config.operation_ip || '',
    default_author: account.config.default_author || '',
    default_cover_media_id: account.config.default_cover_media_id || '',
    default_cover_url: account.config.default_cover_url || '',
    allow_submit_publish: Boolean(account.config.allow_submit_publish),
    allow_public_publish: Boolean(account.config.allow_public_publish),
    enabled: account.status !== 'DISABLED',
  })
  drawer.value = true
}

async function save(closeDrawer = true): Promise<boolean> {
  if (!current.value) return false
  try {
    if (current.value.platform === 'WECHAT_OFFICIAL') {
      form.auth_type = form.publish_mode === 'BROWSER_DRAFT' ? 'QR_LOGIN' : 'APP_SECRET'
    }
    const payload: Record<string, unknown> = { ...form }
    if (!form.app_secret) delete payload.app_secret
    if (!form.access_token) delete payload.access_token
    if (!form.refresh_token) delete payload.refresh_token
    if (!form.token_expires_at) delete payload.token_expires_at
    if (!form.redirect_uri) delete payload.redirect_uri
    if (!form.operation_ip) delete payload.operation_ip
    if (!form.default_cover_url) delete payload.default_cover_url
    await workflowApi.savePlatformAccount(current.value.platform, payload)
    ElMessage.success('平台账号配置已保存')
    if (closeDrawer) drawer.value = false
    await load()
    return true
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
    return false
  }
}

async function test(account: PlatformAccount) {
  testing.value = account.platform
  try {
    const result = await workflowApi.testPlatformAccount(account.platform)
    if (result.result.success) {
      ElMessage.success(
        account.platform === 'XIAOHONGSHU'
          ? '小红书本地登录状态验证通过'
          : account.platform === 'TOUTIAO'
            ? '今日头条本机登录状态验证通过'
            : account.platform === 'WECHAT_OFFICIAL' && account.publishMode === 'BROWSER_DRAFT'
              ? '微信公众号本机登录状态验证通过'
              : '官方接口验证通过',
      )
    } else {
      ElMessage.error(
        [result.result.error_message, result.result.suggested_action].filter(Boolean).join(' '),
      )
    }
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    testing.value = ''
    await load()
  }
}

function stopXhsLoginPolling() {
  if (qrPollTimer) window.clearInterval(qrPollTimer)
  qrPollTimer = undefined
  qrPolling.value = false
}

function startXhsLoginPolling() {
  stopXhsLoginPolling()
  qrPolling.value = true
  const expiresAt = Date.now() + 4 * 60_000
  qrPollTimer = window.setInterval(async () => {
    if (Date.now() >= expiresAt) {
      stopXhsLoginPolling()
      qrMessage.value = '二维码已过期，请重新获取。'
      return
    }
    try {
      const result = await workflowApi.testPlatformAccount(qrPlatform.value)
      if (!result.result.success) return
      stopXhsLoginPolling()
      qrDialog.value = false
      qrImage.value = ''
      await load()
      current.value = accounts.value.find((item) => item.platform === qrPlatform.value)
      ElMessage.success(`${result.platformName}账号 ${result.loginUsername || ''} 登录成功`)
    } catch {
      // The MCP server can be busy while waiting for the QR scan. Keep polling
      // until the QR expires instead of showing a new error every few seconds.
    }
  }, 3000)
}

async function loadXhsQrcode(account?: PlatformAccount) {
  if (account) current.value = account
  qrPlatform.value = 'XIAOHONGSHU'
  qrLoading.value = true
  qrImage.value = ''
  qrMessage.value = ''
  qrDialog.value = true
  try {
    const result = await workflowApi.xiaohongshuLoginQrcode()
    qrImage.value = result.imageDataUrl
    qrMessage.value = result.message
    startXhsLoginPolling()
  } catch (error) {
    qrDialog.value = false
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    qrLoading.value = false
  }
}

async function loadToutiaoQrcode(account?: PlatformAccount) {
  if (account) current.value = account
  qrPlatform.value = 'TOUTIAO'
  qrLoading.value = true
  qrImage.value = ''
  qrMessage.value = ''
  qrDialog.value = true
  try {
    const result = await workflowApi.toutiaoLoginQrcode()
    if (result.connected) {
      qrDialog.value = false
      await load()
      ElMessage.success('今日头条账号已经登录')
      return
    }
    qrImage.value = result.imageDataUrl
    qrMessage.value = result.message
    startXhsLoginPolling()
  } catch (error) {
    qrDialog.value = false
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    qrLoading.value = false
  }
}

async function loadWechatQrcode(account?: PlatformAccount) {
  if (account) current.value = account
  qrPlatform.value = 'WECHAT_OFFICIAL'
  qrLoading.value = true
  qrImage.value = ''
  qrMessage.value = ''
  qrDialog.value = true
  try {
    const result = await workflowApi.wechatLoginQrcode()
    if (result.connected) {
      qrDialog.value = false
      await load()
      ElMessage.success('微信公众号已登录')
      return
    }
    qrImage.value = result.imageDataUrl
    qrMessage.value = result.message
    startXhsLoginPolling()
  } catch (error) {
    qrDialog.value = false
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    qrLoading.value = false
  }
}

async function loadXhsQrcodeFromEditor() {
  if (!form.account_name.trim()) form.account_name = 'ContentPilot 小红书'
  form.publish_mode = 'MCP_PUBLISH'
  if (!(await save(false))) return
  current.value = accounts.value.find((item) => item.platform === 'XIAOHONGSHU')
  await loadXhsQrcode(current.value)
}

async function logoutXhs() {
  try {
    await ElMessageBox.confirm(
      '将退出当前小红书本地登录并清除 MCP Cookie，退出后需要重新扫码。确定继续吗？',
      '退出小红书登录',
      { type: 'warning' },
    )
    await workflowApi.xiaohongshuLogout()
    ElMessage.success('已退出小红书登录，可以重新扫码')
    await load()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(getApiErrorMessage(error))
  }
}

async function loadToutiaoQrcodeFromEditor() {
  if (!form.account_name.trim()) form.account_name = 'ContentPilot 今日头条'
  form.auth_type = 'QR_LOGIN'
  form.publish_mode = 'BROWSER_PUBLISH'
  if (!(await save(false))) return
  current.value = accounts.value.find((item) => item.platform === 'TOUTIAO')
  await loadToutiaoQrcode(current.value)
}

async function logoutToutiao() {
  try {
    await ElMessageBox.confirm(
      '将清除本机今日头条登录会话，之后需要重新扫码。确定继续吗？',
      '退出今日头条登录',
      { type: 'warning' },
    )
    await workflowApi.toutiaoLogout()
    ElMessage.success('已退出今日头条登录')
    await load()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(getApiErrorMessage(error))
  }
}

async function loadWechatQrcodeFromEditor() {
  if (!form.account_name.trim()) form.account_name = 'ContentPilot 公众号'
  form.auth_type = 'QR_LOGIN'
  form.publish_mode = 'BROWSER_DRAFT'
  if (!(await save(false))) return
  current.value = accounts.value.find((item) => item.platform === 'WECHAT_OFFICIAL')
  await loadWechatQrcode(current.value)
}

async function logoutWechat() {
  try {
    await ElMessageBox.confirm(
      '将清除本机微信公众号登录会话，之后需要重新扫码。确定继续吗？',
      '退出微信公众号登录',
      { type: 'warning' },
    )
    await workflowApi.wechatLogout()
    ElMessage.success('已退出微信公众号登录')
    await load()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(getApiErrorMessage(error))
  }
}

function qrPlatformName(): string {
  if (qrPlatform.value === 'TOUTIAO') return '今日头条'
  if (qrPlatform.value === 'WECHAT_OFFICIAL') return '微信公众号'
  return '小红书'
}

function qrScannerName(): string {
  if (qrPlatform.value === 'TOUTIAO') return '抖音或今日头条'
  if (qrPlatform.value === 'WECHAT_OFFICIAL') return '微信'
  return '小红书'
}

async function disconnect(account: PlatformAccount) {
  try {
    await ElMessageBox.confirm(
      account.platform === 'XIAOHONGSHU'
        ? '将退出小红书本地登录、清除 MCP Cookie，并删除 ContentPilot 中的账号配置。确定继续吗？'
        : account.platform === 'TOUTIAO'
          ? '将清除本机今日头条会话，并删除 ContentPilot 中的账号配置。确定继续吗？'
          : '将删除该平台配置及保存的所有 Token 和密钥，确定继续吗？',
      '解除连接',
      {
        type: 'warning',
      },
    )
    await workflowApi.disconnectPlatformAccount(account.platform)
    ElMessage.success('平台配置已删除，敏感凭证已清除')
    await load()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(getApiErrorMessage(error))
  }
}

async function oauth(platform: Platform) {
  try {
    if (platform === 'X' && !xOAuthCredentialsReady.value) {
      ElMessage.warning('请先在 X Developer Portal 创建应用，并填写 Client ID 和 Client Secret')
      openOfficialPlatform()
      return
    }
    if (!form.redirect_uri.trim()) {
      ElMessage.warning('请填写与 X Developer Portal 完全一致的 Redirect URI')
      return
    }
    if (!(await save(false))) return
    if (!form.redirect_uri) return
    const result =
      platform === 'X'
        ? await workflowApi.startXOAuth(form.redirect_uri)
        : await workflowApi.startWeiboOAuth(form.redirect_uri)
    window.location.assign(result.authorizationUrl)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  }
}

function openOfficialPlatform() {
  const url = current.value?.connectionGuide.consoleUrl
  if (!url) return
  window.open(url, '_blank', 'noopener,noreferrer')
}

async function showLogs(account: PlatformAccount) {
  current.value = account
  logs.value = await workflowApi.platformAuthLogs(account.platform)
  logDrawer.value = true
}

onMounted(async () => {
  sessionClockTimer = window.setInterval(() => {
    sessionClock.value = Date.now()
  }, 30_000)
  await load()
  if (route.query.oauth === 'weibo_success') {
    ElMessage.success('微博官方 OAuth 授权成功，已取得真实 Access Token')
    await router.replace({ name: 'platform-accounts' })
  } else if (route.query.oauth === 'x_success') {
    ElMessage.success('X 官方 OAuth 授权成功，已取得真实 Access Token')
    await router.replace({ name: 'platform-accounts' })
  } else if (isAdmin.value && typeof route.query.platform === 'string') {
    const requested = accounts.value.find((item) => item.platform === route.query.platform)
    if (requested) edit(requested)
  }
})
onBeforeUnmount(() => {
  stopXhsLoginPolling()
  if (sessionClockTimer) window.clearInterval(sessionClockTimer)
})
</script>

<template>
  <div>
    <PageHeader
      title="平台账号"
      :description="
        isAdmin
          ? '统一管理团队共享的平台授权与发布能力；所有敏感凭证仅加密保存在服务端。'
          : '查看团队共享平台账号的连接和发布能力；授权与敏感配置由管理员维护。'
      "
    >
      <el-button :loading="loading" @click="load"><RefreshCw :size="15" />刷新</el-button>
    </PageHeader>
    <el-alert
      v-if="!isAdmin"
      class="mb-4"
      title="当前为运营者只读视图：你可以检测连接并使用已授权账号发布，但不能查看密钥、扫码授权或解除连接。"
      type="info"
      :closable="false"
    />

    <div v-loading="loading" class="account-grid">
      <article
        v-for="account in accounts"
        :key="account.platform"
        class="account-card"
        :data-testid="`platform-account-${account.platform}`"
      >
        <header>
          <PlatformIcon :platform="account.platform" />
          <div>
            <h2>{{ account.platformName }}</h2>
            <p>{{ account.accountName }}</p>
          </div>
          <el-tag :type="statusType(account.status)" effect="light">
            {{ statusNames[account.status] || account.status }}
          </el-tag>
        </header>

        <div v-if="account.status === 'TOKEN_EXPIRED'" class="account-warning">
          <ShieldAlert :size="16" />授权已过期，请重新授权后再创建真实发布任务。
        </div>
        <div v-if="account.platform === 'XIAOHONGSHU'" class="account-notice">
          {{
            account.publishMode === 'MCP_PUBLISH' && account.localPublishingEnabled
              ? account.status === 'CONNECTED'
                ? `本机 MCP 已登录${account.loginUsername ? `，当前账号：${account.loginUsername}` : ''}。`
                : '本机 MCP 尚未登录，请点击下方“扫码登录”，成功后系统会自动更新状态。'
              : '当前使用人工发布交付包；本地 MCP 自动发布默认关闭，不会伪装成已连接。'
          }}
        </div>
        <div v-else-if="account.platform === 'TOUTIAO'" class="account-notice account-notice--real">
          {{
            account.status === 'CONNECTED'
              ? account.publicPublishEnabled
                ? `本机 Chrome 已登录${account.loginUsername ? `，当前账号：${account.loginUsername}` : ''}；真实发布已开启。`
                : '本机 Chrome 已登录；真实发布安全开关关闭，不会发送文章。'
              : '尚未登录今日头条创作中心，请保存配置后扫码登录。'
          }}
        </div>
        <div
          v-else-if="
            account.platform === 'WECHAT_OFFICIAL' && account.publishMode === 'BROWSER_DRAFT'
          "
          class="account-notice account-notice--real"
        >
          {{
            account.status === 'CONNECTED'
              ? `本机微信公众号已登录${account.loginUsername ? `，当前账号：${account.loginUsername}` : ''}；文章只保存到草稿箱，不会公开发布。`
              : '尚未登录微信公众平台，保存配置后扫码即可使用。'
          }}
        </div>
        <div
          v-else-if="
            account.platform === 'X' &&
            account.status === 'CONNECTED' &&
            !account.publicPublishEnabled
          "
          class="account-notice account-notice--real"
        >
          X OAuth 已连接，但真实发布开关仍为关闭状态；连接测试不会发送帖子。
        </div>
        <div v-else-if="account.status !== 'CONNECTED'" class="account-notice account-notice--real">
          尚未通过官方接口验证。保存真实平台凭证并完成授权前，系统不会创建发布任务。
        </div>

        <dl class="account-meta">
          <div>
            <dt>发布方式</dt>
            <dd>{{ publishModeLabel(account) }}</dd>
          </div>
          <div>
            <dt>最近检测</dt>
            <dd>{{ account.lastTestAt ? formatDateTime(account.lastTestAt) : '尚未检测' }}</dd>
          </div>
          <div
            v-if="
              ['XIAOHONGSHU', 'TOUTIAO'].includes(account.platform) ||
              (account.platform === 'WECHAT_OFFICIAL' && account.publishMode === 'BROWSER_DRAFT')
            "
          >
            <dt>登录账号</dt>
            <dd>{{ account.loginUsername || '尚未获取' }}</dd>
          </div>
          <div
            v-if="
              ['XIAOHONGSHU', 'TOUTIAO'].includes(account.platform) ||
              (account.platform === 'WECHAT_OFFICIAL' && account.publishMode === 'BROWSER_DRAFT')
            "
          >
            <dt>上次登录</dt>
            <dd>{{ formatDateTime(account.lastLoginAt) }}</dd>
          </div>
          <div
            v-if="
              ['XIAOHONGSHU', 'TOUTIAO'].includes(account.platform) ||
              (account.platform === 'WECHAT_OFFICIAL' && account.publishMode === 'BROWSER_DRAFT')
            "
          >
            <dt>已登录时长</dt>
            <dd>{{ loginDuration(account) }}</dd>
          </div>
          <div
            v-if="
              ['XIAOHONGSHU', 'TOUTIAO'].includes(account.platform) ||
              (account.platform === 'WECHAT_OFFICIAL' && account.publishMode === 'BROWSER_DRAFT')
            "
          >
            <dt>本机会话</dt>
            <dd>
              {{
                account.status === 'CONNECTED'
                  ? ['TOUTIAO', 'WECHAT_OFFICIAL'].includes(account.platform)
                    ? '已保存在本机 Chrome'
                    : '已保存在 MCP'
                  : '未登录'
              }}
            </dd>
          </div>
          <div v-else>
            <dt>Token</dt>
            <dd>
              {{ account.tokenHint || (account.accessTokenConfigured ? '已配置' : '未配置') }}
            </dd>
          </div>
        </dl>

        <p v-if="account.publishHint" class="account-hint">{{ account.publishHint }}</p>

        <section class="capability-list">
          <p>目标能力（最终以平台审核和接口权限为准）</p>
          <span v-for="capability in account.capabilities" :key="capability">
            <CheckCircle2 :size="13" />{{ capabilityNames[capability] || capability }}
          </span>
        </section>
        <p v-if="account.lastError && account.status !== 'CONNECTED'" class="account-error">
          {{ accountErrorMessage(account) }}
        </p>

        <footer>
          <el-button
            v-if="
              isAdmin &&
              account.id &&
              account.platform === 'WECHAT_OFFICIAL' &&
              account.publishMode === 'BROWSER_DRAFT' &&
              account.status !== 'CONNECTED'
            "
            :loading="qrLoading"
            @click="loadWechatQrcode(account)"
          >
            <QrCode :size="14" />扫码登录
          </el-button>
          <el-button
            v-if="
              isAdmin &&
              account.platform === 'WECHAT_OFFICIAL' &&
              account.publishMode === 'BROWSER_DRAFT' &&
              account.status === 'CONNECTED'
            "
            @click="logoutWechat"
          >
            <Unlink :size="14" />退出登录
          </el-button>
          <el-button
            v-if="
              isAdmin &&
              account.id &&
              account.platform === 'TOUTIAO' &&
              account.status !== 'CONNECTED'
            "
            :loading="qrLoading"
            @click="loadToutiaoQrcode(account)"
          >
            <QrCode :size="14" />扫码登录
          </el-button>
          <el-button
            v-if="isAdmin && account.platform === 'TOUTIAO' && account.status === 'CONNECTED'"
            @click="logoutToutiao"
          >
            <Unlink :size="14" />退出登录
          </el-button>
          <el-button
            v-if="
              isAdmin &&
              account.platform === 'XIAOHONGSHU' &&
              account.localPublishingEnabled &&
              account.publishMode === 'MCP_PUBLISH' &&
              account.status !== 'CONNECTED'
            "
            :loading="qrLoading"
            @click="loadXhsQrcode(account)"
          >
            <QrCode :size="14" />扫码登录
          </el-button>
          <el-button
            v-if="
              isAdmin &&
              account.platform === 'XIAOHONGSHU' &&
              account.localPublishingEnabled &&
              account.publishMode === 'MCP_PUBLISH' &&
              account.status === 'CONNECTED'
            "
            @click="logoutXhs"
          >
            <Unlink :size="14" />退出登录
          </el-button>
          <el-button
            v-if="
              account.platform !== 'XIAOHONGSHU' ||
              (account.localPublishingEnabled && account.publishMode === 'MCP_PUBLISH')
            "
            :disabled="
              !account.id ||
              (['WEIBO', 'X'].includes(account.platform) && !account.accessTokenConfigured) ||
              (account.platform === 'XIAOHONGSHU' && account.publishMode !== 'MCP_PUBLISH')
            "
            :loading="testing === account.platform"
            @click="test(account)"
            ><Link2 :size="14" />{{
              ['WEIBO', 'X'].includes(account.platform) && !account.accessTokenConfigured
                ? '请先完成 OAuth'
                : account.platform === 'XIAOHONGSHU'
                  ? '检测本地登录'
                  : account.platform === 'TOUTIAO'
                    ? '检测本机登录'
                    : account.platform === 'WECHAT_OFFICIAL' &&
                        account.publishMode === 'BROWSER_DRAFT'
                      ? '检测本机登录'
                      : '验证真实连接'
            }}</el-button
          >
          <el-button v-if="isAdmin" type="primary" @click="edit(account)"
            ><Settings2 :size="14" />编辑配置</el-button
          >
          <el-dropdown v-if="isAdmin && account.id" trigger="click">
            <el-button>更多</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="showLogs(account)">授权日志</el-dropdown-item>
                <el-dropdown-item divided @click="disconnect(account)">
                  <Unlink :size="13" />解除连接
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </footer>
      </article>
    </div>

    <el-drawer v-model="drawer" :title="`${title}配置`" size="520px">
      <el-form v-if="current" label-position="top" data-testid="platform-account-form">
        <section class="connection-guide">
          <div>
            <b>真实连接步骤</b>
            <a :href="current.connectionGuide.consoleUrl" target="_blank" rel="noopener noreferrer"
              >打开官方平台</a
            >
          </div>
          <ol>
            <li v-for="step in current.connectionGuide.steps" :key="step">{{ step }}</li>
          </ol>
        </section>
        <el-form-item label="账号名称" required>
          <el-input v-model="form.account_name" placeholder="用于 ContentPilot 内部识别" />
        </el-form-item>

        <template v-if="current.platform === 'WEIBO'">
          <el-form-item label="App Key / Client ID" required
            ><el-input v-model="form.client_id"
          /></el-form-item>
          <el-form-item label="App Secret"
            ><el-input
              v-model="form.app_secret"
              type="password"
              show-password
              placeholder="留空表示保持原值"
          /></el-form-item>
          <el-form-item label="Redirect URI" required
            ><el-input v-model="form.redirect_uri"
          /></el-form-item>
          <el-form-item label="发布操作用户公网 IP">
            <el-input v-model="form.operation_ip" placeholder="填写实际公网 IPv4 或 IPv6" />
            <small class="field-help"
              >微博发布接口要求 rip 参数。请填写实际点击排期或发布的操作用户公网
              IP；系统能直接识别公网访问时会优先使用当次请求 IP。</small
            >
          </el-form-item>
          <el-form-item label="Access Token"
            ><el-input
              v-model="form.access_token"
              type="password"
              show-password
              placeholder="可手工录入，推荐使用 OAuth"
          /></el-form-item>
          <el-form-item label="Refresh Token"
            ><el-input v-model="form.refresh_token" type="password" show-password
          /></el-form-item>
          <el-form-item label="Token 到期时间"
            ><el-date-picker
              v-model="form.token_expires_at"
              type="datetime"
              value-format="YYYY-MM-DDTHH:mm:ss"
              class="!w-full"
          /></el-form-item>
          <el-form-item label="发布方式"
            ><el-tag type="success">微博官方 OAuth API</el-tag></el-form-item
          >
          <el-alert
            title="真实发布权限取决于微博开放平台应用审核和账号授权范围。"
            type="info"
            :closable="false"
          />
        </template>

        <template v-else-if="current.platform === 'X'">
          <el-form-item label="OAuth 2.0 Client ID" required
            ><el-input v-model="form.client_id"
          /></el-form-item>
          <el-form-item label="Client Secret">
            <el-input
              v-model="form.app_secret"
              type="password"
              show-password
              placeholder="留空表示保持原值"
            />
          </el-form-item>
          <el-form-item label="Redirect URI" required
            ><el-input v-model="form.redirect_uri"
          /></el-form-item>
          <el-form-item label="发布方式"
            ><el-tag type="success">X 官方 OAuth 2.0 API</el-tag></el-form-item
          >
          <el-checkbox v-model="form.allow_public_publish">
            我已了解真实发布会将内容发送到 X，允许该共享账号创建真实帖子
          </el-checkbox>
          <el-alert
            class="mt-4"
            :title="
              form.allow_public_publish
                ? '公开发布开关已开启。每次立即发布时仍会要求再次确认。'
                : '默认安全模式：仅保存授权并验证连接，不允许创建真实 X 帖子。'
            "
            :type="form.allow_public_publish ? 'warning' : 'info'"
            :closable="false"
          />
          <el-alert
            class="mt-3"
            title="需要在 X Developer Portal 中启用 OAuth 2.0，并授予 tweet.read、tweet.write、users.read、offline.access。连接测试只读取账号信息，不会发送测试帖。"
            type="info"
            :closable="false"
          />
        </template>

        <template v-else-if="current.platform === 'WECHAT_OFFICIAL'">
          <el-form-item label="连接方式">
            <el-radio-group v-model="form.publish_mode">
              <el-radio-button value="BROWSER_DRAFT">本机扫码（推荐）</el-radio-button>
              <el-radio-button value="DRAFT_ONLY">官方 API</el-radio-button>
              <el-radio-button value="SUBMIT_PUBLISH">官方 API 提交发布</el-radio-button>
            </el-radio-group>
          </el-form-item>

          <template v-if="form.publish_mode === 'BROWSER_DRAFT'">
            <el-alert
              title="微信扫码后登录状态仅保存在这台电脑。文章只保存到公众号草稿箱，不会公开发布。"
              type="info"
              :closable="false"
            />
            <el-button class="mt-4" :loading="qrLoading" @click="loadWechatQrcodeFromEditor">
              <QrCode :size="15" />保存并获取登录二维码
            </el-button>
          </template>

          <template v-else>
            <el-form-item label="AppID" required><el-input v-model="form.app_id" /></el-form-item>
            <el-form-item label="AppSecret"
              ><el-input
                v-model="form.app_secret"
                type="password"
                show-password
                placeholder="留空表示保持原值"
            /></el-form-item>
            <el-form-item label="默认封面素材 ID"
              ><el-input v-model="form.default_cover_media_id" placeholder="没有选择本地封面时使用"
            /></el-form-item>
            <el-form-item label="默认封面 URL"
              ><el-input v-model="form.default_cover_url"
            /></el-form-item>
            <el-checkbox
              v-if="form.publish_mode === 'SUBMIT_PUBLISH'"
              v-model="form.allow_submit_publish"
              >我已确认该公众号具备发布接口权限，允许提交发布</el-checkbox
            >
            <el-alert
              class="mt-4"
              title="请在公众平台配置服务器出口 IP 白名单。建议先使用只创建草稿模式。"
              type="warning"
              :closable="false"
            />
          </template>
          <el-form-item label="默认作者"><el-input v-model="form.default_author" /></el-form-item>
        </template>

        <template v-else-if="current.platform === 'TOUTIAO'">
          <el-form-item label="发布方式">
            <el-tag type="success">本机 Chrome 扫码登录与真实文章发布</el-tag>
          </el-form-item>
          <el-checkbox v-model="form.allow_public_publish">
            我已了解真实发布会将文章发送到今日头条，允许该共享账号发布真实内容
          </el-checkbox>
          <el-alert
            class="mt-4"
            :title="
              form.allow_public_publish
                ? '真实发布已开启；建议先扫码并检测账号，再发布一篇测试文章。'
                : '安全模式：可以扫码和检测登录，但不会向今日头条发送文章。'
            "
            :type="form.allow_public_publish ? 'warning' : 'info'"
            :closable="false"
          />
          <el-button class="mt-4" :loading="qrLoading" @click="loadToutiaoQrcodeFromEditor">
            <QrCode :size="15" />保存并获取登录二维码
          </el-button>
        </template>

        <template v-else>
          <el-form-item label="发布方式">
            <el-select v-model="form.publish_mode" class="w-full">
              <el-option label="人工发布交付（默认）" value="MANUAL_CONFIRM" />
              <el-option
                label="本地 xiaohongshu-mcp 试运行（仅自己可见）"
                value="MCP_PUBLISH"
                :disabled="!current.localPublishingEnabled"
              />
            </el-select>
          </el-form-item>
          <el-alert
            v-if="!current.localPublishingEnabled"
            title="本地 MCP 发布默认关闭。当前只生成文案与图片交付包，不会保存小红书 Cookie 或伪装发布成功。"
            type="warning"
            :closable="false"
          />
          <template v-else-if="form.publish_mode === 'MCP_PUBLISH'">
            <el-alert
              title="实验性本地功能：Cookie 只由本机 xiaohongshu-mcp 保存。首次建议使用“仅自己可见”验证，平台风控或页面变化可能导致失败。"
              type="warning"
              :closable="false"
            />
            <el-button class="mt-4" :loading="qrLoading" @click="loadXhsQrcodeFromEditor">
              <QrCode :size="15" />获取扫码登录二维码
            </el-button>
          </template>
          <el-alert
            v-else
            title="人工交付模式不会操作浏览器；排期到点后生成文案与图片发布包。"
            type="info"
            :closable="false"
          />
        </template>
      </el-form>
      <template #footer>
        <div class="drawer-actions">
          <el-button @click="drawer = false">取消</el-button>
          <el-button
            v-if="current?.platform === 'X' && !xOAuthCredentialsReady"
            tag="a"
            :href="current.connectionGuide.consoleUrl"
            target="_blank"
            rel="noopener noreferrer"
            type="primary"
            plain
            data-testid="open-x-developer-portal"
          >
            第 1 步：打开 X 开发者后台
          </el-button>
          <el-button
            v-if="
              current &&
              ['WEIBO', 'X'].includes(current.platform) &&
              form.publish_mode === 'REAL_API' &&
              (current.platform !== 'X' || xOAuthCredentialsReady)
            "
            :data-testid="`start-${current.platform.toLowerCase()}-oauth`"
            @click="oauth(current.platform)"
            >保存并前往{{ current.platform === 'X' ? ' X' : '微博' }}官方授权</el-button
          >
          <el-button type="primary" data-testid="save-platform-account" @click="save()"
            >保存配置</el-button
          >
        </div>
      </template>
    </el-drawer>

    <el-drawer v-model="logDrawer" title="平台授权日志" size="520px">
      <el-timeline v-if="logs.length">
        <el-timeline-item
          v-for="(item, index) in logs"
          :key="index"
          :timestamp="String(item.createdAt || '')"
        >
          <b>{{ item.action }} · {{ item.status }}</b>
          <p>{{ item.message }}</p>
        </el-timeline-item>
      </el-timeline>
      <el-empty v-else description="暂无授权日志" />
    </el-drawer>

    <el-dialog
      v-model="qrDialog"
      :title="`${qrPlatformName()}扫码登录`"
      width="420px"
      @closed="stopXhsLoginPolling"
    >
      <div v-loading="qrLoading" class="qr-login-panel">
        <img v-if="qrImage" :src="qrImage" :alt="`${qrPlatformName()}登录二维码`" />
        <el-empty v-else-if="!qrLoading" description="没有收到二维码" />
        <p v-if="qrMessage">{{ qrMessage }}</p>
        <small v-if="qrPolling"
          >请使用{{ qrScannerName() }} App 扫码，系统正在自动检测登录结果。</small
        >
        <small v-else>二维码过期后可以重新获取。</small>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.account-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}
.account-card {
  border: 1px solid var(--color-line, #e5e7eb);
  border-radius: 16px;
  background: white;
  padding: 20px;
  box-shadow: 0 8px 28px rgb(15 23 42 / 5%);
}
.account-card header {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 12px;
}
.account-card h2 {
  font-size: 17px;
  font-weight: 650;
}
.account-card header p,
.account-meta dt {
  color: #64748b;
  font-size: 12px;
}
.qr-login-panel {
  min-height: 260px;
  display: grid;
  place-items: center;
  gap: 12px;
  text-align: center;
}
.qr-login-panel img {
  width: 240px;
  height: 240px;
  object-fit: contain;
}
.qr-login-panel p,
.qr-login-panel small {
  color: #64748b;
  line-height: 1.6;
}
.account-warning,
.account-notice {
  display: flex;
  gap: 7px;
  margin-top: 16px;
  padding: 10px 12px;
  border-radius: 10px;
  font-size: 12px;
  line-height: 1.6;
  background: #fff7ed;
  color: #9a3412;
}
.account-notice {
  background: #f8fafc;
  color: #475569;
}
.account-notice--real {
  background: #fff7ed;
  color: #9a3412;
}
.account-meta {
  display: grid;
  gap: 10px;
  margin-top: 18px;
}
.account-meta div {
  display: flex;
  justify-content: space-between;
  gap: 16px;
}
.account-meta dd {
  text-align: right;
  font-size: 13px;
}
.capability-list {
  margin-top: 18px;
}
.capability-list p {
  margin-bottom: 9px;
  color: #64748b;
  font-size: 12px;
}
.capability-list span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin: 0 6px 6px 0;
  padding: 5px 8px;
  border-radius: 999px;
  background: #f1f5f9;
  color: #334155;
  font-size: 12px;
}
.account-error {
  margin-top: 10px;
  color: #dc2626;
  font-size: 12px;
}
.account-hint {
  margin-top: 14px;
  padding: 8px 12px;
  border-radius: 8px;
  background: #ecfdf5;
  color: #065f46;
  font-size: 12px;
  line-height: 1.6;
}
.account-card footer {
  display: flex;
  gap: 8px;
  margin-top: 18px;
  flex-wrap: wrap;
}
.drawer-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.connection-guide {
  margin-bottom: 20px;
  border: 1px solid #bfdbfe;
  border-radius: 12px;
  background: #eff6ff;
  padding: 14px 16px;
  color: #1e3a5f;
  font-size: 12px;
  line-height: 1.65;
}
.connection-guide > div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.connection-guide a {
  color: #1677ff;
  font-weight: 600;
}
.connection-guide ol {
  margin: 9px 0 0;
  padding-left: 20px;
}
.field-help {
  display: block;
  margin-top: 6px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.55;
}
@media (max-width: 1100px) {
  .account-grid {
    grid-template-columns: 1fr;
  }
}
</style>
