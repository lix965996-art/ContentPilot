<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowUpRight, Settings, Share2, Users } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import PageHeader from '@/components/PageHeader.vue'
import PlatformIcon from '@/components/PlatformIcon.vue'
import Skeleton from '@/components/Skeleton.vue'
import { apiClient, getApiErrorMessage } from '@/api/client'
import { workflowApi } from '@/api/workflow'
import type { PlatformAccount } from '@/types/business'

const statusLabels: Record<string, string> = {
  NOT_CONFIGURED: '未配置',
  CONNECTING: '连接中',
  CONNECTED: '已连接',
  TOKEN_EXPIRED: '令牌过期',
  INVALID: '无效',
  DISABLED: '已禁用',
  MANUAL_ONLY: '仅手动',
  READY: '就绪',
  LOGIN_REQUIRED: '需登录',
  FAILED: '失败',
}

const router = useRouter()
const loading = ref(true)
const accounts = ref<PlatformAccount[]>([])
const userStats = ref({ userCount: 0, activeUserCount: 0 })
const serviceStatus = ref<Record<string, unknown>>({})

const connectedCount = computed(
  () => accounts.value.filter((item) => item.status === 'CONNECTED').length,
)
const attentionCount = computed(
  () =>
    accounts.value.filter((item) =>
      ['LOGIN_REQUIRED', 'TOKEN_EXPIRED', 'FAILED', 'DISABLED'].includes(item.status),
    ).length,
)

async function load() {
  loading.value = true
  try {
    const [accountRows, summaryRes] = await Promise.all([
      workflowApi.platformAccounts(),
      apiClient.get('/dashboard/summary'),
    ])
    accounts.value = accountRows
    serviceStatus.value = summaryRes.data.data?.serviceStatus || {}
    const overviewRes = await apiClient.get('/admin/overview')
    userStats.value = overviewRes.data.data || { userCount: 0, activeUserCount: 0 }
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <PageHeader
      title="系统概览"
      description="只管系统：平台连接、用户账号、全局配置。内容运营请使用运营者账号。"
    />

    <Skeleton v-if="loading" :lines="5" />

    <template v-else>
      <section class="admin-metric-grid">
        <article>
          <span>平台已连接</span>
          <strong>{{ connectedCount }} / {{ accounts.length }}</strong>
          <small>团队共享账号</small>
        </article>
        <article>
          <span>待处理连接</span>
          <strong>{{ attentionCount }}</strong>
          <small>需扫码或补配置</small>
        </article>
        <article>
          <span>系统用户</span>
          <strong>{{ userStats.activeUserCount }} / {{ userStats.userCount }}</strong>
          <small>启用 / 总数</small>
        </article>
        <article>
          <span>运行模式</span>
          <strong>{{ serviceStatus.demoMode ? '演示' : '正式' }}</strong>
          <small>API · 数据库 · 鉴权正常</small>
        </article>
      </section>

      <section class="mt-4 grid gap-4 lg:grid-cols-2">
        <article class="panel p-5">
          <div class="flex items-center justify-between">
            <div>
              <p class="section-label">平台</p>
              <h2 class="section-title mt-1">各平台连接状态</h2>
            </div>
            <el-button @click="router.push({ name: 'platform-accounts' })">去配置</el-button>
          </div>
          <div class="mt-4 space-y-3">
            <div
              v-for="account in accounts"
              :key="account.platform"
              class="flex items-center gap-3 rounded-xl border border-line px-4 py-3"
            >
              <PlatformIcon :platform="account.platform" size="sm" />
              <div class="min-w-0 flex-1">
                <p class="text-sm font-medium">{{ account.platformName }}</p>
                <p class="truncate text-xs text-muted">{{ account.accountName || '未配置' }}</p>
              </div>
              <el-tag
                :type="
                  account.status === 'CONNECTED'
                    ? 'success'
                    : account.status === 'LOGIN_REQUIRED'
                      ? 'warning'
                      : 'info'
                "
                round
              >
                {{ statusLabels[account.status] || account.status }}
              </el-tag>
            </div>
          </div>
        </article>

        <article class="panel p-5">
          <p class="section-label">快捷入口</p>
          <h2 class="section-title mt-1">管理员常做事项</h2>
          <div class="mt-4 grid gap-3">
            <button class="admin-action" @click="router.push({ name: 'platform-accounts' })">
              <Share2 :size="18" />
              <span><b>平台账号</b><small>扫码登录、API Key、发布模式</small></span>
              <ArrowUpRight :size="16" />
            </button>
            <button class="admin-action" @click="router.push({ name: 'settings' })">
              <Settings :size="18" />
              <span><b>系统设置</b><small>大模型、用户、审计日志</small></span>
              <ArrowUpRight :size="16" />
            </button>
            <button class="admin-action" @click="router.push({ name: 'settings' })">
              <Users :size="18" />
              <span><b>用户与权限</b><small>在设置页管理账号角色</small></span>
              <ArrowUpRight :size="16" />
            </button>
          </div>
        </article>
      </section>
    </template>
  </div>
</template>

<style scoped>
.admin-metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}
.admin-metric-grid article {
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  background: #fff;
  padding: 16px 18px;
}
.admin-metric-grid span {
  display: block;
  color: #667085;
  font-size: 12px;
}
.admin-metric-grid strong {
  display: block;
  margin-top: 8px;
  color: #172033;
  font-size: 24px;
  line-height: 1.1;
}
.admin-metric-grid small {
  display: block;
  margin-top: 6px;
  color: #98a2b3;
  font-size: 11px;
}
.admin-action {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  background: #fff;
  padding: 14px 16px;
  text-align: left;
}
.admin-action b {
  display: block;
  color: #172033;
  font-size: 14px;
}
.admin-action small {
  display: block;
  margin-top: 2px;
  color: #667085;
  font-size: 12px;
}
.admin-action svg:last-child {
  margin-left: auto;
  color: #98a2b3;
}
@media (max-width: 1024px) {
  .admin-metric-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
