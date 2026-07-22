<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CheckCircle2, Link2, RefreshCw, Settings2, ShieldAlert, Unlink } from 'lucide-vue-next'
import PageHeader from '@/components/PageHeader.vue'
import PlatformIcon from '@/components/PlatformIcon.vue'
import { workflowApi } from '@/api/workflow'
import { getApiErrorMessage } from '@/api/client'
import type { Platform, PlatformAccount } from '@/types/business'

const accounts = ref<PlatformAccount[]>([])
const loading = ref(false)
const testing = ref<Platform | ''>('')
const drawer = ref(false)
const logDrawer = ref(false)
const logs = ref<Array<Record<string, unknown>>>([])
const current = ref<PlatformAccount>()

const form = reactive({
  account_name: '',
  auth_type: 'NONE',
  publish_mode: 'MOCK',
  app_id: '',
  client_id: '',
  app_secret: '',
  access_token: '',
  refresh_token: '',
  token_expires_at: '',
  redirect_uri: '',
  default_author: '',
  default_cover_media_id: '',
  default_cover_url: '',
  allow_submit_publish: false,
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
  SIMULATED_PUBLISH: '模拟发布',
}
const statusNames: Record<string, string> = {
  NOT_CONFIGURED: '未配置',
  CONNECTING: '待检测',
  CONNECTED: '已连接',
  TOKEN_EXPIRED: 'Token 已过期',
  INVALID: '连接无效',
  DISABLED: '已停用',
}
const statusType = (status: string) =>
  status === 'CONNECTED' ? 'success' : status === 'CONNECTING' ? 'warning' : 'danger'
const title = computed(() => current.value?.platformName || '平台配置')

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
    account_name: account.accountName === '未配置' ? '' : account.accountName,
    auth_type:
      account.platform === 'WEIBO'
        ? 'OAUTH2'
        : account.platform === 'WECHAT_OFFICIAL'
          ? 'APP_SECRET'
          : 'NONE',
    publish_mode:
      account.platform === 'XIAOHONGSHU' ? 'MANUAL_CONFIRM' : account.publishMode || 'MOCK',
    app_id: account.appId,
    client_id: account.clientId,
    app_secret: '',
    access_token: '',
    refresh_token: '',
    token_expires_at: account.tokenExpiresAt?.slice(0, 16) || '',
    redirect_uri:
      account.config.redirect_uri ||
      'http://127.0.0.1:8000/api/platform-accounts/WEIBO/oauth/callback',
    default_author: account.config.default_author || '',
    default_cover_media_id: account.config.default_cover_media_id || '',
    default_cover_url: account.config.default_cover_url || '',
    allow_submit_publish: Boolean(account.config.allow_submit_publish),
    enabled: account.status !== 'DISABLED',
  })
  drawer.value = true
}

async function save() {
  if (!current.value) return
  try {
    const payload: Record<string, unknown> = { ...form }
    if (!form.app_secret) delete payload.app_secret
    if (!form.access_token) delete payload.access_token
    if (!form.refresh_token) delete payload.refresh_token
    if (!form.token_expires_at) delete payload.token_expires_at
    if (!form.redirect_uri) delete payload.redirect_uri
    if (!form.default_cover_url) delete payload.default_cover_url
    await workflowApi.savePlatformAccount(current.value.platform, payload)
    ElMessage.success('平台账号配置已保存')
    drawer.value = false
    await load()
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  }
}

async function test(account: PlatformAccount) {
  testing.value = account.platform
  try {
    const result = await workflowApi.testPlatformAccount(account.platform)
    ElMessage.success(result.result.success ? '连接测试通过' : '连接测试未通过')
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    testing.value = ''
    await load()
  }
}

async function disconnect(account: PlatformAccount) {
  try {
    await ElMessageBox.confirm('将清除该账号保存的所有 Token 和密钥，确定继续吗？', '解除连接', {
      type: 'warning',
    })
    await workflowApi.disconnectPlatformAccount(account.platform)
    ElMessage.success('连接已解除，敏感凭证已清除')
    await load()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(getApiErrorMessage(error))
  }
}

async function oauth() {
  try {
    await save()
    if (!form.redirect_uri) return
    const result = await workflowApi.startWeiboOAuth(form.redirect_uri)
    window.location.assign(result.authorizationUrl)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  }
}

async function showLogs(account: PlatformAccount) {
  current.value = account
  logs.value = await workflowApi.platformAuthLogs(account.platform)
  logDrawer.value = true
}

onMounted(() => load().catch((error) => ElMessage.error(getApiErrorMessage(error))))
</script>

<template>
  <div>
    <PageHeader
      title="平台账号"
      description="管理官方授权、发布能力与 Token 状态；所有敏感凭证仅加密保存在服务端。"
    >
      <el-button :loading="loading" @click="load"><RefreshCw :size="15" />刷新</el-button>
    </PageHeader>

    <div v-loading="loading" class="account-grid">
      <article v-for="account in accounts" :key="account.platform" class="account-card">
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
          小红书当前采用人工确认发布，不属于服务器无人值守自动发布。
        </div>

        <dl class="account-meta">
          <div>
            <dt>发布方式</dt>
            <dd>{{ account.publishMode }}</dd>
          </div>
          <div>
            <dt>最近检测</dt>
            <dd>
              {{
                account.lastTestAt
                  ? new Date(account.lastTestAt).toLocaleString('zh-CN')
                  : '尚未检测'
              }}
            </dd>
          </div>
          <div>
            <dt>Token</dt>
            <dd>
              {{ account.tokenHint || (account.accessTokenConfigured ? '已配置' : '未配置') }}
            </dd>
          </div>
        </dl>

        <section class="capability-list">
          <p>发布能力</p>
          <span v-for="capability in account.capabilities" :key="capability">
            <CheckCircle2 :size="13" />{{ capabilityNames[capability] || capability }}
          </span>
        </section>
        <p v-if="account.lastError" class="account-error">{{ account.lastError }}</p>

        <footer>
          <el-button
            :disabled="!account.id"
            :loading="testing === account.platform"
            @click="test(account)"
            ><Link2 :size="14" />测试连接</el-button
          >
          <el-button type="primary" @click="edit(account)"
            ><Settings2 :size="14" />编辑配置</el-button
          >
          <el-dropdown v-if="account.id" trigger="click">
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
            ><el-radio-group v-model="form.publish_mode"
              ><el-radio-button value="MOCK">Mock</el-radio-button
              ><el-radio-button value="REAL_API">官方 API</el-radio-button></el-radio-group
            ></el-form-item
          >
          <el-alert
            title="真实发布权限取决于微博开放平台应用审核和账号授权范围。"
            type="info"
            :closable="false"
          />
        </template>

        <template v-else-if="current.platform === 'WECHAT_OFFICIAL'">
          <el-form-item label="AppID" required><el-input v-model="form.app_id" /></el-form-item>
          <el-form-item label="AppSecret"
            ><el-input
              v-model="form.app_secret"
              type="password"
              show-password
              placeholder="留空表示保持原值"
          /></el-form-item>
          <el-form-item label="默认作者"><el-input v-model="form.default_author" /></el-form-item>
          <el-form-item label="默认封面素材 ID"
            ><el-input v-model="form.default_cover_media_id" placeholder="没有选择本地封面时使用"
          /></el-form-item>
          <el-form-item label="默认封面 URL"
            ><el-input v-model="form.default_cover_url"
          /></el-form-item>
          <el-form-item label="发布方式"
            ><el-select v-model="form.publish_mode" class="w-full"
              ><el-option label="Mock 草稿箱" value="MOCK" /><el-option
                label="自动进入草稿箱"
                value="DRAFT_ONLY" /><el-option
                label="提交发布"
                value="SUBMIT_PUBLISH" /></el-select
          ></el-form-item>
          <el-checkbox v-model="form.allow_submit_publish"
            >我已确认该公众号具备发布接口权限，允许提交发布</el-checkbox
          >
          <el-alert
            class="mt-4"
            title="请在公众平台配置服务器出口 IP 白名单。默认推荐只创建草稿，由运营人员检查后发布。"
            type="warning"
            :closable="false"
          />
        </template>

        <template v-else>
          <el-form-item label="发布方式"
            ><el-radio-group v-model="form.publish_mode"
              ><el-radio-button value="MANUAL_CONFIRM">人工确认</el-radio-button
              ><el-radio-button value="MOCK">Mock</el-radio-button></el-radio-group
            ></el-form-item
          >
          <el-alert
            title="不会保存小红书 Cookie 或密码，也不会执行 Selenium、Playwright 或浏览器注入。排期到点后生成文案与图片发布包。"
            type="warning"
            :closable="false"
          />
        </template>
      </el-form>
      <template #footer>
        <div class="drawer-actions">
          <el-button @click="drawer = false">取消</el-button>
          <el-button
            v-if="current?.platform === 'WEIBO' && form.publish_mode === 'REAL_API'"
            @click="oauth"
            >保存并前往微博授权</el-button
          >
          <el-button type="primary" data-testid="save-platform-account" @click="save"
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
  </div>
</template>

<style scoped>
.account-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
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
@media (max-width: 1100px) {
  .account-grid {
    grid-template-columns: 1fr;
  }
}
</style>
