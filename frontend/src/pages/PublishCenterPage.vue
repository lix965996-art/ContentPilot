<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Clipboard,
  Download,
  ExternalLink,
  Inbox,
  RefreshCw,
  Rocket,
  ScrollText,
} from 'lucide-vue-next'
import EmptyState from '@/components/EmptyState.vue'
import PageHeader from '@/components/PageHeader.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { workflowApi } from '@/api/workflow'
import { getApiErrorMessage } from '@/api/client'
import type { PublishPackage, Schedule } from '@/types/business'
import { platformNames } from '@/types/business'
import type { Platform } from '@/types/business'
import { presentOperationError } from '@/utils/operation-error'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const isAdmin = computed(() => auth.hasRole(['ADMIN']))
const rows = ref<Schedule[]>([])
const loading = ref(false)
const detail = ref<Schedule>()
const drawer = ref(false)
const status = ref('')
const publishPackage = ref<PublishPackage>()
const publishModeNames: Record<string, string> = {
  REAL_API: '官方 API 发布',
  DRAFT_ONLY: '同步到草稿箱',
  SUBMIT_PUBLISH: '提交平台发布',
  MANUAL_CONFIRM: '人工发布确认',
  MCP_PUBLISH: '本机自动发布',
  BROWSER_DRAFT: '本机浏览器保存草稿',
}
function publishModeLabel(platform: string, mode: string): string {
  if (platform === 'WEIBO' && mode === 'REAL_API') return '微博官方 API'
  if (platform === 'X' && mode === 'REAL_API') return 'X 官方 API（真实发布）'
  return publishModeNames[mode] || mode
}
const statusTabs = [
  ['全部', ''],
  ['待发布', 'PENDING'],
  ['发布中', 'PUBLISHING'],
  ['等待确认', 'WAITING_MANUAL_CONFIRM'],
  ['已完成', 'PUBLISHED,DRAFT_CREATED,PUBLISH_SUBMITTED,MANUAL_PUBLISHED'],
  ['失败', 'FAILED'],
]
async function load() {
  loading.value = true
  try {
    rows.value = await workflowApi.schedules(status.value ? { status: status.value } : {})
  } finally {
    loading.value = false
  }
}
async function open(row: Schedule) {
  detail.value = await workflowApi.schedule(row.id)
  publishPackage.value = undefined
  if (detail.value.platform === 'XIAOHONGSHU' && detail.value.publishPackageJson) {
    publishPackage.value = detail.value.publishPackageJson
  }
  drawer.value = true
}
async function action(row: Schedule, name: string) {
  try {
    if (name === 'publish-now') {
      await ElMessageBox.confirm(
        `将使用“${row.accountName || '未命名账号'}”立即执行${publishModeLabel(row.platform, row.publishMode)}。${
          row.platform === 'XIAOHONGSHU' && row.publishMode === 'MCP_PUBLISH'
            ? '当前发布范围为“仅自己可见”。'
            : row.platform === 'X'
              ? '这会通过 X 官方 API 发送真实帖子，内容可能立即公开可见。'
              : ''
        }是否继续？`,
        '确认立即发布',
      )
      if (row.platform === 'X') {
        await ElMessageBox.prompt(
          `请再次确认发布账号“${row.accountName || '未命名账号'}”。输入“发布到X”后才能继续。`,
          '真实发布二次确认',
          {
            inputPlaceholder: '发布到X',
            inputValidator: (value) => value === '发布到X' || '请输入“发布到X”',
            confirmButtonText: '确认真实发布',
            type: 'warning',
          },
        )
      }
    }
    let data: Record<string, unknown> = {}
    if (name === 'manual-confirm') {
      const answer = await ElMessageBox.prompt(
        '请填写平台公开发布链接，系统会据此记录真实发布时间。',
        '确认人工发布',
        {
          inputPlaceholder: 'https://www.xiaohongshu.com/explore/...',
          inputPattern: /^https?:\/\/.+/,
          inputErrorMessage: '请输入有效的 HTTP(S) 链接',
          confirmButtonText: '我已发布',
        },
      )
      data = { published_url: answer.value }
    }
    await workflowApi.scheduleAction(row.id, name, data)
    ElMessage.success('操作成功')
    await load()
    if (drawer.value) await open(row)
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(getApiErrorMessage(e))
  }
}
async function copyPackage() {
  if (!publishPackage.value) return
  const text = `${publishPackage.value.title}\n\n${publishPackage.value.content}\n\n${publishPackage.value.hashtags.join(' ')}`
  await navigator.clipboard.writeText(text)
  ElMessage.success('文案已复制')
}
async function downloadPackage() {
  if (!detail.value) return
  await workflowApi.downloadPublishPackage(detail.value.id)
}
function openCreator() {
  if (publishPackage.value?.creatorUrl)
    window.open(publishPackage.value.creatorUrl, '_blank', 'noopener')
}
onMounted(load)
function platformLabel(value: string): string {
  return platformNames[value as Platform] || value
}
function rowClassName({ row }: { row: Schedule }) {
  return row.status === 'FAILED' ? 'failed-row' : ''
}
function selectStatus(value: string) {
  status.value = value
  void load()
}
function logDisplayMessage(log: Record<string, unknown>) {
  const raw = String(log.responseSummary || log.errorMessage || '')
  if (!raw) return '该步骤没有补充说明。'
  const looksTechnical =
    Boolean(log.errorMessage) ||
    /\b(?:rid|request.?id|external_id|default_cover_media_id)\b|api unauthorized|\[\d{4,}\]|[{}]/i.test(
      raw,
    )
  if (!looksTechnical) return raw
  const issue = presentOperationError(raw, {
    type: 'PUBLISH',
    platform: detail.value?.platform,
  })
  return issue ? `${issue.title}：${issue.description}` : '该步骤未完成，请检查发布设置后重试。'
}
function logStepLabel(value: unknown) {
  const labels: Record<string, string> = {
    PREPARE: '准备发布内容',
    UPLOAD_MEDIA: '上传素材',
    CREATE_DRAFT: '创建平台草稿',
    SUBMIT_PUBLISH: '提交平台发布',
    PUBLISH: '执行发布',
    MANUAL_CONFIRM: '人工确认',
  }
  return labels[String(value)] || '执行发布流程'
}
function logStatusLabel(value: unknown) {
  const labels: Record<string, string> = {
    PENDING: '等待执行',
    RUNNING: '执行中',
    SUCCESS: '已完成',
    FAILED: '未完成',
    RETRYING: '重新尝试',
  }
  return labels[String(value)] || '状态待确认'
}
</script>
<template>
  <div>
    <PageHeader title="发布中心" description="跟踪排期执行、人工确认、失败重试和逐步日志。"
      ><el-button :loading="loading" @click="load"
        ><RefreshCw :size="15" class="mr-2" />刷新</el-button
      ></PageHeader
    >
    <div class="content-tabs publish-tabs">
      <button
        v-for="tab in statusTabs"
        :key="tab[0]"
        :class="{ active: status === tab[1] }"
        @click="selectStatus(tab[1])"
      >
        {{ tab[0] }}
      </button>
    </div>
    <section class="data-surface">
      <el-table v-loading="loading" :data="rows" :row-class-name="rowClassName"
        ><el-table-column label="任务 / 内容" min-width="310"
          ><template #default="{ row }"
            ><button class="text-left" @click="open(row)">
              <span class="block text-xs text-muted"
                >#{{ row.id }} · {{ platformLabel(row.platform) }}</span
              ><span class="mt-1 block font-medium text-ink">{{ row.articleTitle }}</span>
            </button></template
          ></el-table-column
        ><el-table-column label="计划时间" width="175"
          ><template #default="{ row }">{{
            new Date(row.scheduledAt).toLocaleString('zh-CN', {
              month: '2-digit',
              day: '2-digit',
              hour: '2-digit',
              minute: '2-digit',
            })
          }}</template></el-table-column
        ><el-table-column label="方式" width="145"
          ><template #default="{ row }">{{
            publishModeLabel(row.platform, row.publishMode)
          }}</template></el-table-column
        ><el-table-column label="状态" width="155"
          ><template #default="{ row }"
            ><StatusBadge :status="row.status" /></template></el-table-column
        ><el-table-column label="重试" width="80"
          ><template #default="{ row }">{{ row.retryCount }}/3</template></el-table-column
        ><el-table-column label="操作" width="230"
          ><template #default="{ row }"
            ><el-button
              v-if="row.status === 'PENDING'"
              link
              type="primary"
              @click="action(row, 'publish-now')"
              ><Rocket :size="14" class="mr-1" />立即发布</el-button
            ><el-button
              v-if="row.status === 'FAILED'"
              link
              type="danger"
              @click="action(row, 'retry')"
              >重试</el-button
            ><el-button
              v-if="row.status === 'WAITING_MANUAL_CONFIRM'"
              link
              type="success"
              @click="action(row, 'manual-confirm')"
              >确认完成</el-button
            ><el-button link @click="open(row)"
              ><ScrollText :size="14" class="mr-1" />日志</el-button
            ></template
          ></el-table-column
        ><template #empty
          ><EmptyState title="当前没有发布任务"
            ><template #icon><Inbox :size="25" /></template></EmptyState></template
      ></el-table>
    </section>
    <el-drawer v-model="drawer" title="发布任务详情" size="480px"
      ><template v-if="detail"
        ><div class="space-y-5">
          <div class="flex items-start justify-between">
            <div>
              <p class="text-xs text-muted">任务 #{{ detail.id }}</p>
              <h3 class="mt-1 text-lg font-semibold">{{ detail.articleTitle }}</h3>
            </div>
            <StatusBadge :status="detail.status" />
          </div>
          <dl class="info-list">
            <div>
              <dt>平台</dt>
              <dd>{{ platformLabel(detail.platform) }}</dd>
            </div>
            <div>
              <dt>方式</dt>
              <dd>{{ publishModeLabel(detail.platform, detail.publishMode) }}</dd>
            </div>
            <div>
              <dt>发布账号</dt>
              <dd>{{ detail.accountName || '—' }}</dd>
            </div>
            <div>
              <dt>计划时间</dt>
              <dd>{{ new Date(detail.scheduledAt).toLocaleString('zh-CN') }}</dd>
            </div>
            <div>
              <dt>发布链接</dt>
              <dd class="break-all">{{ detail.publishedUrl || '—' }}</dd>
            </div>
            <div>
              <dt>结果类型</dt>
              <dd>
                {{
                  detail.resultMode
                    ? publishModeLabel(detail.platform, detail.resultMode)
                    : '尚无发布结果'
                }}
              </dd>
            </div>
            <div v-if="isAdmin">
              <dt>平台任务 ID</dt>
              <dd class="break-all">{{ detail.externalId || '—' }}</dd>
            </div>
          </dl>
          <section v-if="publishPackage" class="reason-card">
            <p class="font-medium">小红书人工发布包</p>
            <el-alert
              class="mt-3"
              :title="publishPackage.notice"
              type="warning"
              :closable="false"
            />
            <h4 class="mt-4 font-medium">{{ publishPackage.title }}</h4>
            <p class="mt-2 whitespace-pre-wrap text-sm leading-6">{{ publishPackage.content }}</p>
            <div class="mt-3 flex flex-wrap gap-2">
              <el-tag v-for="tag in publishPackage.hashtags" :key="tag">{{ tag }}</el-tag>
            </div>
            <div class="mt-4 flex flex-wrap gap-2">
              <el-button @click="copyPackage"><Clipboard :size="14" />复制文案</el-button>
              <el-button @click="downloadPackage"><Download :size="14" />下载全部图片</el-button>
              <el-button type="primary" @click="openCreator"
                ><ExternalLink :size="14" />打开创作页面</el-button
              >
            </div>
          </section>
          <div>
            <p class="section-label">执行日志</p>
            <div v-if="detail.logs?.length" class="timeline mt-3">
              <div v-for="(log, index) in detail.logs" :key="index">
                <i />
                <div>
                  <p class="font-medium">
                    {{ logStepLabel(log.step) }} · {{ logStatusLabel(log.status) }}
                  </p>
                  <p class="mt-1 text-xs text-muted">
                    {{ logDisplayMessage(log) }}
                  </p>
                </div>
              </div>
            </div>
            <div v-else class="mt-3 text-sm text-muted">任务尚未产生执行日志。</div>
          </div>
        </div></template
      ></el-drawer
    >
  </div>
</template>
