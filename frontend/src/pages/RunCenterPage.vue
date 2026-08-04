<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import {
  Activity,
  Bot,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Coins,
  Layers3,
  RefreshCw,
  RotateCcw,
  Search,
  Send,
  Sparkles,
  TriangleAlert,
  X,
} from 'lucide-vue-next'
import EmptyState from '@/components/EmptyState.vue'
import PlatformIcon from '@/components/PlatformIcon.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { workflowApi } from '@/api/workflow'
import { getApiErrorMessage } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import type { OperationRun, OperationStep, Platform } from '@/types/business'
import { platformNames } from '@/types/business'
import {
  presentOperationError,
  redactTechnicalError,
  type OperationErrorAction,
} from '@/utils/operation-error'

const router = useRouter()
const auth = useAuthStore()
const rows = ref<OperationRun[]>([])
const selected = ref<OperationRun>()
const detailOpen = ref(false)
const loading = ref(false)
const retrying = ref('')
const runType = ref('')
const status = ref('')
const query = ref('')
const summary = ref({ total: 0, running: 0, failed: 0, success: 0 })

const knownPlatforms: Platform[] = ['WEIBO', 'XIAOHONGSHU', 'WECHAT_OFFICIAL', 'TOUTIAO', 'X']
const selectedSteps = computed(() => selected.value?.steps || [])
const isAdmin = computed(() => auth.canManageSystem)
const selectedTechnicalError = computed(() => {
  if (!selected.value) return ''
  const errors = [
    selected.value.errorMessage,
    ...selected.value.steps
      .filter((step) => step.status === 'FAILED')
      .flatMap((step) => [step.error, step.message]),
  ].filter((message): message is string => Boolean(message?.trim()))
  return [...new Set(errors)].join('\n')
})
const selectedIssue = computed(() =>
  presentOperationError(selectedTechnicalError.value, {
    type: selected.value?.type,
    platform: selected.value?.subtitle,
  }),
)
const selectedTechnicalErrorRedacted = computed(() =>
  redactTechnicalError(selectedTechnicalError.value),
)
const successRate = computed(() =>
  summary.value.total ? Math.round((summary.value.success / summary.value.total) * 100) : 0,
)

function typeLabel(type: OperationRun['type']) {
  return type === 'GENERATION' ? 'AI 创作' : '内容发布'
}

function typeDescription(type: OperationRun['type']) {
  return type === 'GENERATION' ? '多平台内容生成' : '平台发布流程'
}

function platformFromValue(value = ''): Platform | undefined {
  return knownPlatforms.find((platform) => value === platform || value.startsWith(`${platform} `))
}

function runPlatforms(run: OperationRun): Platform[] {
  if (run.type === 'GENERATION') {
    return run.steps
      .map((step) => platformFromValue(step.name))
      .filter((platform): platform is Platform => Boolean(platform))
  }
  const platform = platformFromValue(run.subtitle)
  return platform ? [platform] : []
}

function stepName(run: OperationRun, value: string) {
  if (run.type === 'GENERATION') return platformNames[value as Platform] || value
  const labels: Record<string, string> = {
    PREPARE: '准备发布内容',
    UPLOAD_MEDIA: '上传媒体',
    CREATE_DRAFT: '创建草稿',
    SUBMIT_PUBLISH: '提交发布',
    PUBLISH: '执行发布',
    MANUAL_CONFIRM: '人工确认',
    等待调度: '等待调度',
  }
  return labels[value] || value
}

function stageLabel(value?: string) {
  const labels: Record<string, string> = {
    QUEUED: '等待执行',
    RUNNING: '正在处理',
    GENERATING: '生成内容',
    VALIDATING: '校验结果',
    REVIEWING: '质量评审',
    RETRYING: '重新尝试',
    COMPLETED: '处理完成',
    FAILED: '处理失败',
    PREPARING: '准备发布',
    UPLOADING: '上传素材',
    PUBLISHING: '提交平台',
  }
  return value ? labels[value] || '执行流程' : '执行流程'
}

function runReference(run: OperationRun) {
  const segments = String(run.id).split(':')
  const raw = segments[segments.length - 1] || String(run.id)
  return `运行 #${raw.slice(0, 8).toUpperCase()}`
}

function duration(value = 0) {
  if (!value) return '—'
  if (value < 1000) return `${value} ms`
  const seconds = value / 1000
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)} 秒`
  const minutes = Math.floor(seconds / 60)
  const remaining = Math.round(seconds % 60)
  return `${minutes} 分 ${remaining} 秒`
}

function formatTime(value: string) {
  return new Date(value).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatFullTime(value: string) {
  return new Date(value).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function formatTokens(value?: number) {
  if (!value) return '—'
  return new Intl.NumberFormat('zh-CN').format(value)
}

function progressStatus(run: OperationRun) {
  if (['FAILED', 'PARTIAL_SUCCESS'].includes(run.status)) return 'exception'
  if (['SUCCESS', 'DRAFT_CREATED', 'PUBLISH_SUBMITTED', 'MANUAL_PUBLISHED'].includes(run.status)) {
    return 'success'
  }
  return undefined
}

function openDetails(run: OperationRun) {
  selected.value = run
  detailOpen.value = true
}

async function load() {
  loading.value = true
  try {
    const data = await workflowApi.operationRuns({
      run_type: runType.value,
      status: status.value,
      query: query.value,
    })
    rows.value = data.items
    summary.value = data.summary
    if (selected.value) {
      selected.value = rows.value.find((item) => item.id === selected.value?.id)
    }
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '运行记录加载失败'))
  } finally {
    loading.value = false
  }
}

async function retryStep(run: OperationRun, key?: string) {
  retrying.value = key || run.id
  try {
    if (run.type === 'GENERATION' && key) {
      await workflowApi.retryTaskPlatform(String(run.sourceId), key as Platform)
    } else if (run.type === 'PUBLISH') {
      await workflowApi.scheduleAction(Number(run.sourceId), 'retry')
    }
    ElMessage.success('已创建重试任务')
    await load()
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '重试失败'))
  } finally {
    retrying.value = ''
  }
}

function canRetryPlatform(run: OperationRun, step: OperationStep) {
  return (
    run.type === 'GENERATION' &&
    step.status === 'FAILED' &&
    Boolean(platformFromValue(step.name)) &&
    selectedIssue.value?.retryRecommended !== false
  )
}

function stepMessage(step: OperationStep) {
  if (step.status !== 'FAILED') return step.message || '等待执行'
  return selectedIssue.value
    ? '该步骤未完成，请先按上方建议处理后再重试。'
    : '该步骤未完成，请检查设置后重试。'
}

async function goToIssueAction(action?: OperationErrorAction) {
  if (!action) return
  detailOpen.value = false
  await router.push({ name: action })
}

function canUseIssueAction(action?: OperationErrorAction) {
  return Boolean(action && (action !== 'settings' || isAdmin.value))
}

onMounted(load)
</script>

<template>
  <div class="run-center-page">
    <div class="run-page-actions">
      <p>查看 AI 创作和内容发布的实时状态，失败任务可以从中断处继续。</p>
      <el-button :loading="loading" @click="load">
        <RefreshCw :size="15" class="mr-1" />刷新
      </el-button>
    </div>

    <section class="run-metrics" aria-label="运行概览">
      <article class="run-metric-card is-total">
        <span class="run-metric-icon"><Activity :size="18" /></span>
        <div>
          <small>全部运行</small><strong>{{ summary.total }}</strong>
        </div>
        <span class="run-metric-note">当前筛选结果</span>
      </article>
      <article class="run-metric-card is-running">
        <span class="run-metric-icon"><Clock3 :size="18" /></span>
        <div>
          <small>正在执行</small><strong>{{ summary.running }}</strong>
        </div>
        <span class="run-metric-note">实时更新</span>
      </article>
      <article class="run-metric-card is-attention">
        <span class="run-metric-icon"><TriangleAlert :size="18" /></span>
        <div>
          <small>需要处理</small><strong>{{ summary.failed }}</strong>
        </div>
        <span class="run-metric-note">查看原因与处理建议</span>
      </article>
      <article class="run-metric-card is-success">
        <span class="run-metric-icon"><CheckCircle2 :size="18" /></span>
        <div>
          <small>运行成功</small><strong>{{ summary.success }}</strong>
        </div>
        <span class="run-metric-note">成功率 {{ successRate }}%</span>
      </article>
    </section>

    <section class="run-command-bar" aria-label="运行记录筛选">
      <el-segmented
        v-model="runType"
        :options="[
          { label: '全部', value: '' },
          { label: 'AI 创作', value: 'GENERATION' },
          { label: '内容发布', value: 'PUBLISH' },
        ]"
        @change="load"
      />
      <div class="run-command-spacer" />
      <el-select v-model="status" clearable placeholder="全部状态" @change="load">
        <el-option label="执行中" value="ACTIVE" />
        <el-option label="成功" value="SUCCESS" />
        <el-option label="需要处理" value="ATTENTION" />
        <el-option label="等待执行" value="PENDING" />
      </el-select>
      <el-input
        v-model="query"
        clearable
        placeholder="搜索内容标题"
        @keyup.enter="load"
        @clear="load"
      >
        <template #prefix><Search :size="15" /></template>
      </el-input>
    </section>

    <section v-loading="loading" class="run-records-panel">
      <header class="run-records-heading">
        <div>
          <h2>运行记录</h2>
          <p>优先查看失败和执行中的任务，点击任意记录可查看完整步骤。</p>
        </div>
        <span>共 {{ rows.length }} 条</span>
      </header>

      <div v-if="rows.length" class="run-record-table">
        <div class="run-record-header" aria-hidden="true">
          <span>内容</span>
          <span>类型</span>
          <span>目标平台</span>
          <span>状态</span>
          <span>耗时 / Token</span>
          <span>开始时间</span>
          <span />
        </div>

        <button
          v-for="run in rows"
          :key="run.id"
          type="button"
          class="run-record-row"
          :data-status="run.status"
          :aria-label="`查看运行记录：${run.title}`"
          @click="openDetails(run)"
        >
          <span class="run-content-cell">
            <i :data-type="run.type">
              <Bot v-if="run.type === 'GENERATION'" :size="18" />
              <Send v-else :size="17" />
            </i>
            <span>
              <b>{{ run.title }}</b>
              <small>{{ typeDescription(run.type) }} · {{ run.progress }}% 完成</small>
            </span>
          </span>
          <span class="run-type-cell">
            <Sparkles v-if="run.type === 'GENERATION'" :size="14" />
            <Send v-else :size="14" />
            {{ typeLabel(run.type) }}
          </span>
          <span class="run-platform-cell">
            <template v-if="runPlatforms(run).length">
              <span v-for="platform in runPlatforms(run)" :key="platform">
                <PlatformIcon :platform="platform" size="sm" />
                {{ platformNames[platform] }}
              </span>
            </template>
            <small v-else>流程任务</small>
          </span>
          <span><StatusBadge :status="run.status" /></span>
          <span class="run-consumption-cell">
            <b>{{ duration(run.durationMs) }}</b>
            <small>{{ formatTokens(run.tokenUsage) }} Token</small>
          </span>
          <span class="run-time-cell">
            <b>{{ formatTime(run.createdAt) }}</b>
            <small v-if="run.retryCount">已重试 {{ run.retryCount }} 次</small>
            <small v-else>首次执行</small>
          </span>
          <ChevronRight class="run-row-arrow" :size="17" />
        </button>
      </div>

      <EmptyState v-else title="没有符合条件的运行记录">
        <template #icon><Activity :size="26" /></template>
      </EmptyState>
    </section>

    <el-drawer
      v-model="detailOpen"
      class="run-detail-drawer"
      size="640px"
      :with-header="false"
      append-to-body
    >
      <template v-if="selected">
        <header class="run-drawer-header">
          <div class="run-drawer-title">
            <i :data-type="selected.type">
              <Bot v-if="selected.type === 'GENERATION'" :size="20" />
              <Send v-else :size="19" />
            </i>
            <div>
              <span>{{ typeLabel(selected.type) }} · {{ runReference(selected) }}</span>
              <h2>{{ selected.title }}</h2>
            </div>
          </div>
          <div class="run-drawer-actions">
            <StatusBadge :status="selected.status" />
            <button type="button" aria-label="关闭运行详情" @click="detailOpen = false">
              <X :size="19" />
            </button>
          </div>
        </header>

        <section class="run-drawer-progress">
          <div>
            <span>整体进度</span>
            <b>{{ selected.progress }}%</b>
          </div>
          <el-progress
            :percentage="selected.progress"
            :status="progressStatus(selected)"
            :show-text="false"
            :stroke-width="8"
          />
          <p>
            开始于 {{ formatFullTime(selected.createdAt) }}
            <template v-if="selected.scheduledAt">
              · 计划 {{ formatFullTime(selected.scheduledAt) }}
            </template>
          </p>
        </section>

        <section class="run-detail-metrics">
          <article>
            <Clock3 :size="16" /><span>总耗时</span><b>{{ duration(selected.durationMs) }}</b>
          </article>
          <article>
            <Coins :size="16" /><span>Token</span><b>{{ formatTokens(selected.tokenUsage) }}</b>
          </article>
          <article>
            <Layers3 :size="16" /><span>执行步骤</span><b>{{ selectedSteps.length }}</b>
          </article>
          <article>
            <RotateCcw :size="16" /><span>重试次数</span><b>{{ selected.retryCount || 0 }}</b>
          </article>
        </section>

        <section v-if="selected.modelName || selected.provider" class="run-model-strip">
          <span>模型服务</span>
          <b>{{ selected.provider || '默认服务商' }} / {{ selected.modelName || '默认模型' }}</b>
        </section>

        <section v-if="selectedIssue" class="run-resolution-card" role="alert">
          <span class="run-resolution-icon"><TriangleAlert :size="18" /></span>
          <div class="run-resolution-body">
            <h3>{{ selectedIssue.title }}</h3>
            <p>{{ selectedIssue.description }}</p>
            <div
              v-if="
                canUseIssueAction(selectedIssue.primaryAction) ||
                canUseIssueAction(selectedIssue.secondaryAction)
              "
              class="run-resolution-actions"
            >
              <el-button
                v-if="canUseIssueAction(selectedIssue.primaryAction)"
                type="primary"
                size="small"
                @click="goToIssueAction(selectedIssue.primaryAction)"
              >
                {{ selectedIssue.primaryActionLabel }}
              </el-button>
              <el-button
                v-if="canUseIssueAction(selectedIssue.secondaryAction)"
                size="small"
                @click="goToIssueAction(selectedIssue.secondaryAction)"
              >
                {{ selectedIssue.secondaryActionLabel }}
              </el-button>
            </div>
            <details v-if="isAdmin && selectedTechnicalError" class="run-technical-details">
              <summary>查看技术详情（仅管理员）</summary>
              <pre>{{ selectedTechnicalErrorRedacted }}</pre>
            </details>
          </div>
        </section>

        <section class="run-step-section">
          <header>
            <div>
              <h3>执行步骤</h3>
              <p>每个平台独立执行，单个平台失败不会影响其他结果。</p>
            </div>
            <span>{{ selectedSteps.length }} 步</span>
          </header>

          <div class="run-step-list">
            <article
              v-for="(step, index) in selectedSteps"
              :key="step.key"
              class="run-step-card"
              :data-status="step.status"
            >
              <div class="run-step-marker">
                <PlatformIcon
                  v-if="platformFromValue(step.name)"
                  :platform="platformFromValue(step.name)!"
                  size="sm"
                />
                <span v-else>{{ index + 1 }}</span>
              </div>
              <div class="run-step-body">
                <header>
                  <div>
                    <b>{{ stepName(selected, step.name) }}</b>
                    <small>{{ stageLabel(step.stage) }}</small>
                  </div>
                  <StatusBadge :status="step.status" />
                </header>
                <p>{{ stepMessage(step) }}</p>
                <el-progress
                  :percentage="step.progress"
                  :status="
                    step.status === 'FAILED'
                      ? 'exception'
                      : step.status === 'SUCCESS'
                        ? 'success'
                        : undefined
                  "
                  :show-text="false"
                  :stroke-width="5"
                />
                <footer>
                  <span><Clock3 :size="13" />{{ duration(step.durationMs) }}</span>
                  <span v-if="step.tokenUsage"
                    ><Coins :size="13" />{{ formatTokens(step.tokenUsage) }} Token</span
                  >
                  <span v-if="step.attempt">第 {{ step.attempt }} 次执行</span>
                </footer>
                <el-button
                  v-if="canRetryPlatform(selected, step)"
                  size="small"
                  :loading="retrying === step.key"
                  @click="retryStep(selected, step.key)"
                >
                  <RotateCcw :size="13" class="mr-1" />仅重试该平台
                </el-button>
              </div>
            </article>
          </div>
        </section>

        <footer
          v-if="
            selected.type === 'PUBLISH' &&
            selected.status === 'FAILED' &&
            selectedIssue?.retryRecommended !== false
          "
        >
          <el-button
            type="primary"
            :loading="retrying === selected.id"
            @click="retryStep(selected)"
          >
            <RotateCcw :size="14" class="mr-1" />从失败处重新发布
          </el-button>
        </footer>
      </template>
    </el-drawer>
  </div>
</template>
