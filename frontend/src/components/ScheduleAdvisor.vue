<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  CalendarClock,
  ChartNoAxesColumn,
  CircleAlert,
  Database,
  Gauge,
  Lightbulb,
  Sparkles,
  TriangleAlert,
} from 'lucide-vue-next'
import { getApiErrorMessage } from '@/api/client'
import { workflowApi } from '@/api/workflow'
import {
  accountStatusNames,
  defaultPublishMode,
  formatLocalDateTime,
  publishModeOptions,
} from '@/composables/usePublishModes'
import type {
  Platform,
  PlatformAccount,
  PublishMode,
  PublishTimeRecommendation,
  ScheduleConflict,
  TimeSource,
  TimeWindow,
} from '@/types/business'
import { platformNames } from '@/types/business'

const timeWindowOptions: Array<{ value: TimeWindow; label: string }> = [
  { value: '90D', label: '最近90天' },
  { value: '30D', label: '最近30天' },
  { value: 'ALL', label: '全部时间' },
  { value: 'CUSTOM', label: '自定义范围' },
]

const props = defineProps<{
  articleId?: number
  variantId?: number
  platform: Platform
  accounts: PlatformAccount[]
  reviewStatus?: string
}>()
const emit = defineEmits<{ scheduled: [scheduleId: number] }>()

const loading = ref(false)
const creating = ref(false)
const result = ref<PublishTimeRecommendation>()
const choice = ref<'RECOMMENDED' | 'ALTERNATIVE_0' | 'ALTERNATIVE_1' | 'CUSTOM'>('RECOMMENDED')
const customTime = ref('')
const accountId = ref<number>()
const publishMode = ref<PublishMode>('REAL_API')
const conflicts = ref<ScheduleConflict[]>([])
const conflictChecked = ref(false)
const windowMode = ref<TimeWindow>('90D')
const windowStartDate = ref('')
const windowEndDate = ref('')

const availableAccounts = computed(() =>
  props.accounts.filter((item) => item.platform === props.platform && item.id),
)
const selectedAccount = computed(() =>
  availableAccounts.value.find((item) => item.id === accountId.value),
)
const modeOptions = computed(() => publishModeOptions(props.platform, selectedAccount.value))
const confidenceLabels: Record<string, string> = {
  HIGH: '高',
  MEDIUM: '中',
  LOW: '低',
}
const weightRows = computed(() => {
  const weights = result.value?.weights
  if (!weights) return []
  return [
    { key: '公开基线', value: weights.baseline },
    { key: '账号历史', value: weights.history },
    { key: '内容类型', value: weights.content },
    { key: '作息时段', value: weights.timezone },
  ].map((item) => ({ ...item, percent: Math.round(item.value * 100) }))
})

const selectedTime = computed(() => {
  if (!result.value) return ''
  if (choice.value === 'CUSTOM') return customTime.value
  if (choice.value === 'RECOMMENDED') return result.value.recommendedAt.slice(0, 16)
  const index = choice.value === 'ALTERNATIVE_0' ? 0 : 1
  return result.value.alternatives[index]?.recommendedAt.slice(0, 16) || ''
})
const timeSource = computed<TimeSource>(() =>
  choice.value === 'RECOMMENDED'
    ? 'RECOMMENDED'
    : choice.value === 'CUSTOM'
      ? 'CUSTOM'
      : 'ALTERNATIVE',
)

function formatMoment(value?: string): string {
  if (!value) return '—'
  return new Date(value).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function syncAccount() {
  const account = availableAccounts.value[0]
  accountId.value = account?.id || undefined
  publishMode.value = defaultPublishMode(props.platform, account)
}

async function calculate() {
  if (!props.articleId) return ElMessage.warning('请先选择原文')
  if (windowMode.value === 'CUSTOM' && (!windowStartDate.value || !windowEndDate.value)) {
    return ElMessage.warning('自定义时间范围需要填写开始和结束日期')
  }
  loading.value = true
  try {
    result.value = await workflowApi.recommend({
      article_id: props.articleId,
      variant_id: props.variantId,
      platform: props.platform,
      account_id: accountId.value,
      horizon_days: 7,
      window: windowMode.value,
      window_start_date: windowMode.value === 'CUSTOM' ? windowStartDate.value : undefined,
      window_end_date: windowMode.value === 'CUSTOM' ? windowEndDate.value : undefined,
    })
    choice.value = 'RECOMMENDED'
    customTime.value = result.value.recommendedAt.slice(0, 16)
    await checkConflict()
    ElMessage.success('排期建议已生成')
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '推荐时间计算失败'))
  } finally {
    loading.value = false
  }
}

async function checkConflict() {
  if (!selectedTime.value) return
  try {
    const data = await workflowApi.scheduleConflictCheck({
      platform: props.platform,
      scheduled_at: `${selectedTime.value}:00`,
      account_id: accountId.value,
    })
    conflicts.value = data.conflicts
    conflictChecked.value = true
  } catch {
    conflicts.value = []
    conflictChecked.value = false
  }
}

async function addToSchedule() {
  if (!props.articleId || !props.variantId) return ElMessage.warning('请先选择平台版本')
  if (!selectedTime.value) return ElMessage.warning('请选择发布时间')
  if (props.reviewStatus !== 'APPROVED') {
    return ElMessage.warning('请先完成审核，再加入排期')
  }
  if (
    (props.platform !== 'XIAOHONGSHU' || publishMode.value === 'MCP_PUBLISH') &&
    !accountId.value
  ) {
    return ElMessage.warning('请先在“平台账号”页面配置并选择账号')
  }
  creating.value = true
  try {
    const schedule = await workflowApi.createSchedule({
      article_id: props.articleId,
      variant_id: props.variantId,
      account_id: accountId.value,
      platform: props.platform,
      scheduled_at: `${selectedTime.value}:00`,
      publish_mode: publishMode.value,
      recommendation_id: result.value?.id,
      time_source: timeSource.value,
      content_type: result.value?.contentType,
    })
    emit('scheduled', schedule.id)
    ElMessage.success('已加入排期日历')
    await checkConflict()
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '加入排期失败'))
  } finally {
    creating.value = false
  }
}

function useNow() {
  customTime.value = formatLocalDateTime(new Date(Date.now() + 3_600_000)).slice(0, 16)
  choice.value = 'CUSTOM'
}

watch(
  () => props.platform,
  () => {
    result.value = undefined
    conflicts.value = []
    syncAccount()
  },
  { immediate: true },
)
watch(() => props.accounts, syncAccount)
watch([choice, customTime], () => void checkConflict())
</script>

<template>
  <section class="schedule-advisor" data-testid="schedule-advisor">
    <header class="advisor-head">
      <div>
        <strong><CalendarClock :size="15" />排期建议</strong>
        <small>{{ platformNames[platform] }} · 由活跃度统计计算，大模型只负责整理说明</small>
      </div>
      <el-button
        size="small"
        type="primary"
        plain
        :loading="loading"
        data-testid="advisor-calculate"
        @click="calculate"
      >
        <Gauge :size="14" />{{ result ? '重新计算' : '计算推荐时间' }}
      </el-button>
    </header>

    <div class="advisor-target">
      <label class="field-label"
        >历史数据范围<el-select v-model="windowMode" class="mt-2 w-full" size="small"
          ><el-option
            v-for="item in timeWindowOptions"
            :key="item.value"
            :label="item.label"
            :value="item.value" /></el-select
      ></label>
      <template v-if="windowMode === 'CUSTOM'">
        <label class="field-label"
          >开始<el-date-picker
            v-model="windowStartDate"
            type="date"
            value-format="YYYY-MM-DD"
            size="small"
            class="mt-2 w-full" /></label
        ><label class="field-label"
          >结束<el-date-picker
            v-model="windowEndDate"
            type="date"
            value-format="YYYY-MM-DD"
            size="small"
            class="mt-2 w-full" /></label
      ></template>
    </div>

    <p v-if="!result" class="advisor-empty">
      还没有排期建议。点击“计算推荐时间”，系统会结合公开活跃基线与已导入的账号历史数据给出发布时段。
    </p>

    <template v-else>
      <div class="advisor-best">
        <span class="icon-tile"><CalendarClock :size="20" /></span>
        <div>
          <b>{{ formatMoment(result.recommendedAt) }}</b>
          <span>
            得分 {{ result.score }} · 置信度
            {{ confidenceLabels[result.confidence] || result.confidence }} ·
            {{ result.contentTypeName }}
          </span>
        </div>
        <em>{{ result.algorithmVersion }}</em>
      </div>

      <p v-if="result.narrative" class="advisor-narrative">
        <Sparkles :size="14" />{{ result.narrative }}
        <small>{{ result.narrativeProvider === 'LLM' ? '大模型整理' : '规则生成' }}</small>
      </p>

      <div v-if="result.warnings.length" class="advisor-warnings">
        <p v-for="item in result.warnings" :key="item"><CircleAlert :size="13" />{{ item }}</p>
      </div>

      <div class="advisor-reasons">
        <div v-for="reason in result.reasons" :key="reason.type" class="reason-card">
          <Lightbulb :size="16" />
          <div>
            <p>{{ reason.description }}</p>
            <small>贡献 {{ reason.contribution }} 分</small>
          </div>
        </div>
      </div>

      <div class="advisor-source">
        <header><Database :size="14" />数据来源与权重</header>
        <ul>
          <li>
            <span>公开基线</span><b>{{ result.dataSource.baseline }}</b>
          </li>
          <li>
            <span>账号历史</span><b>{{ result.dataSource.accountHistory }}</b>
          </li>
          <li>
            <span>样本量</span
            ><b
              >账号 {{ result.accountSampleCount }} 条 / 公开 {{ result.baselineSampleCount }} 条</b
            >
          </li>
          <li>
            <span>数据充足度</span><b>{{ result.dataSufficiency.message }}</b>
          </li>
          <li v-if="result.window">
            <span>分析范围</span
            ><b
              >{{ result.window.label
              }}<template v-if="result.window.startDate">
                （{{ result.window.startDate }} ~ {{ result.window.endDate }}）</template
              ></b
            >
          </li>
        </ul>
        <div class="advisor-weights">
          <div v-for="item in weightRows" :key="item.key">
            <span>{{ item.key }}</span>
            <i><em :style="{ width: `${item.percent}%` }" /></i>
            <b>{{ item.percent }}%</b>
          </div>
        </div>
        <p v-if="result.dataSource.sourceTypes.length" class="advisor-source-tags">
          <span
            v-for="item in result.dataSource.sourceTypes"
            :key="item.sourceType"
            class="meta-chip"
            >{{ item.label }} · {{ item.count }}</span
          >
        </p>
      </div>

      <div class="advisor-choice">
        <header><ChartNoAxesColumn :size="14" />选择发布时间</header>
        <el-radio-group v-model="choice">
          <el-radio value="RECOMMENDED">
            使用推荐时间 · {{ formatMoment(result.recommendedAt) }}
          </el-radio>
          <el-radio
            v-for="(item, index) in result.alternatives"
            :key="item.recommendedAt"
            :value="index === 0 ? 'ALTERNATIVE_0' : 'ALTERNATIVE_1'"
          >
            备选 {{ index + 1 }} · {{ formatMoment(item.recommendedAt) }} · 得分
            {{ item.score }}
          </el-radio>
          <el-radio value="CUSTOM">自定义时间</el-radio>
        </el-radio-group>
        <div class="advisor-custom">
          <el-date-picker
            v-model="customTime"
            type="datetime"
            value-format="YYYY-MM-DDTHH:mm"
            :disabled="choice !== 'CUSTOM'"
            class="!w-full"
          />
          <el-button size="small" text @click="useNow">一小时后</el-button>
        </div>
      </div>

      <div class="advisor-target">
        <label>
          <span>平台账号</span>
          <el-select v-model="accountId" size="small" placeholder="请选择平台账号">
            <el-option
              v-for="account in availableAccounts"
              :key="account.id!"
              :label="`${account.accountName} · ${accountStatusNames[account.status] || account.status}`"
              :value="account.id!"
            />
          </el-select>
        </label>
        <label>
          <span>发布方式</span>
          <el-select v-model="publishMode" size="small">
            <el-option
              v-for="mode in modeOptions"
              :key="mode.value"
              :label="mode.label"
              :value="mode.value"
              :disabled="mode.disabled"
            />
          </el-select>
        </label>
      </div>

      <div v-if="conflicts.length" class="advisor-warnings conflict">
        <p v-for="item in conflicts" :key="item.scheduleId">
          <TriangleAlert :size="13" />{{ item.message
          }}<template v-if="item.articleTitle">（{{ item.articleTitle }}）</template>
        </p>
      </div>
      <p v-else-if="conflictChecked" class="advisor-ok">所选时间没有排期冲突</p>

      <el-button
        type="primary"
        class="advisor-submit"
        :loading="creating"
        data-testid="advisor-schedule"
        @click="addToSchedule"
      >
        <CalendarClock :size="15" />加入排期
      </el-button>
      <small v-if="reviewStatus !== 'APPROVED'" class="advisor-hint">
        当前版本尚未审核通过，审核后才能加入排期。
      </small>
    </template>
  </section>
</template>
