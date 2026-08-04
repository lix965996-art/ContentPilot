<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UploadRequestOptions } from 'element-plus'
import {
  CalendarPlus,
  Clock3,
  Database,
  Download,
  Gauge,
  Lightbulb,
  Sparkles,
  TriangleAlert,
  Upload,
} from 'lucide-vue-next'
import PageHeader from '@/components/PageHeader.vue'
import ChartPanel from '@/components/ChartPanel.vue'
import { workflowApi } from '@/api/workflow'
import { getApiErrorMessage } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import type {
  ActivityAnalysis,
  Article,
  HistoryImportBatch,
  HistoryImportPreview,
  Platform,
  PlatformAccount,
  PublishTimeRecommendation,
  TimeWindow,
  Variant,
} from '@/types/business'
import { analysisPlatformNames, platformNames } from '@/types/business'

const timeWindowOptions: Array<{ value: TimeWindow; label: string }> = [
  { value: '90D', label: '最近90天' },
  { value: '30D', label: '最近30天' },
  { value: 'ALL', label: '全部时间' },
  { value: 'CUSTOM', label: '自定义范围' },
]

const auth = useAuthStore()
const canOperate = computed(() => auth.canManageBusiness)
const tab = ref<'recommend' | 'activity' | 'history'>('activity')

/* ---------- 发布时间推荐（原有能力） ---------- */
const articles = ref<Article[]>([])
const articleId = ref<number>()
const variants = ref<Variant[]>([])
const accounts = ref<PlatformAccount[]>([])
const platform = ref<Platform>('WEIBO')
const accountId = ref<number>()
const recommendWindow = ref<TimeWindow>('90D')
const recommendStartDate = ref('')
const recommendEndDate = ref('')
const result = ref<PublishTimeRecommendation>()
const loading = ref(false)
const calcStep = ref(0)
const calcPercent = ref(0)
let calcTimer: ReturnType<typeof setInterval> | undefined

const CALC_STEPS = [
  '读取内容与平台版本',
  '判定内容类型',
  '加载活跃度样本与时段规则',
  '按权重打分并选出最佳时段',
]

function stopCalcProgress(final = false) {
  if (calcTimer) {
    clearInterval(calcTimer)
    calcTimer = undefined
  }
  if (final) {
    calcStep.value = CALC_STEPS.length
    calcPercent.value = 100
  }
}

function startCalcProgress() {
  stopCalcProgress()
  calcStep.value = 0
  calcPercent.value = 8
  calcTimer = setInterval(() => {
    if (calcStep.value < CALC_STEPS.length - 1) {
      calcStep.value += 1
    }
    calcPercent.value = Math.min(92, calcPercent.value + 12 + Math.floor(Math.random() * 8))
  }, 420)
}

const variant = computed(() => variants.value.find((x) => x.platform === platform.value))
const platformAccounts = computed(() =>
  accounts.value.filter((item) => item.platform === platform.value && item.id),
)
const confidenceLabels: Record<string, string> = { HIGH: '高', MEDIUM: '中', LOW: '低' }
const isColdStart = computed(
  () => !!result.value && (result.value.accountSampleCount || 0) === 0,
)
const option = computed(() => ({
  grid: { left: 40, right: 18, top: 30, bottom: 30 },
  tooltip: { trigger: 'axis' },
  legend: { top: 0, textStyle: { fontSize: 10 } },
  xAxis: {
    type: 'category',
    data: (result.value?.curve || []).map((x) => x.time),
    axisLabel: { interval: 2 },
  },
  yAxis: { type: 'value', min: 0, max: 100 },
  series: [
    {
      name: '公开基线',
      type: 'line',
      smooth: true,
      symbol: 'none',
      areaStyle: { color: 'rgba(0,122,255,.06)' },
      lineStyle: { color: '#007aff', width: 2 },
      data: (result.value?.curve || []).map((x) => x.platformPrior),
    },
    {
      name: '账号历史',
      type: 'line',
      smooth: true,
      symbol: 'none',
      lineStyle: { color: '#f59e0b', width: 2, type: 'dashed' },
      data: (result.value?.curve || []).map((x) => x.accountHistory),
    },
  ],
}))

async function loadArticles() {
  const [data, accountRows] = await Promise.all([
    workflowApi.articles({ page_size: 100 }),
    workflowApi.platformAccounts(),
  ])
  articles.value = data.items
  accounts.value = accountRows
  articleId.value = data.items[0]?.id
  await loadVariants()
}
async function loadVariants() {
  if (!articleId.value) return
  variants.value = await workflowApi.variants(articleId.value)
  result.value = undefined
}
async function calculate() {
  if (!articleId.value || !variant.value)
    return ElMessage.warning('该文章还没有当前平台版本，请先生成平台版本')
  if (recommendWindow.value === 'CUSTOM' && (!recommendStartDate.value || !recommendEndDate.value)) {
    return ElMessage.warning('自定义时间范围需要填写开始和结束日期')
  }
  loading.value = true
  result.value = undefined
  startCalcProgress()
  try {
    result.value = await workflowApi.recommend({
      article_id: articleId.value,
      variant_id: variant.value.id,
      platform: platform.value,
      account_id: accountId.value,
      window: recommendWindow.value,
      window_start_date:
        recommendWindow.value === 'CUSTOM' ? recommendStartDate.value : undefined,
      window_end_date: recommendWindow.value === 'CUSTOM' ? recommendEndDate.value : undefined,
    })
    stopCalcProgress(true)
    ElMessage.success('推荐时间已计算')
  } catch (e) {
    stopCalcProgress()
    calcPercent.value = 0
    calcStep.value = 0
    ElMessage.error(getApiErrorMessage(e))
  } finally {
    loading.value = false
  }
}

/* ---------- 活跃度分析 ---------- */
const analysis = ref<ActivityAnalysis>()
const analysisLoading = ref(false)
const analysisFilter = ref<{
  platform: string
  account_id?: number
  content_type: string
  source_scope: 'ALL' | 'ACCOUNT' | 'BASELINE'
  window: TimeWindow
  start_date: string
  end_date: string
}>({
  platform: 'YOUTUBE',
  content_type: '',
  source_scope: 'BASELINE',
  window: 'ALL',
  start_date: '',
  end_date: '',
})
const contentTypes = ref<Array<{ value: string; label: string }>>([])
const analysisAccounts = computed(() =>
  accounts.value.filter(
    (item) =>
      item.id &&
      (!analysisFilter.value.platform || item.platform === analysisFilter.value.platform),
  ),
)
const weekdayOption = computed(() => ({
  grid: { left: 40, right: 16, top: 22, bottom: 26 },
  tooltip: { trigger: 'axis' },
  xAxis: { type: 'category', data: (analysis.value?.weekday || []).map((x) => x.name) },
  yAxis: { type: 'value' },
  series: [
    {
      type: 'bar',
      barWidth: 22,
      itemStyle: { color: '#2563EB', borderRadius: [4, 4, 0, 0] },
      data: (analysis.value?.weekday || []).map((x) => x.score),
    },
  ],
}))
const hourlyOption = computed(() => ({
  grid: { left: 40, right: 16, top: 22, bottom: 26 },
  tooltip: { trigger: 'axis' },
  xAxis: {
    type: 'category',
    data: (analysis.value?.hourly || []).map((x) => x.time),
    axisLabel: { interval: 2 },
  },
  yAxis: { type: 'value' },
  series: [
    {
      type: 'line',
      smooth: true,
      symbol: 'none',
      areaStyle: { color: 'rgba(37,99,235,.08)' },
      lineStyle: { color: '#2563EB', width: 2 },
      data: (analysis.value?.hourly || []).map((x) => x.score),
    },
  ],
}))
const heatmapOption = computed(() => {
  const rows = analysis.value?.heatmap || []
  const max = Math.max(1, ...rows.map((item) => item.score))
  return {
    grid: { left: 44, right: 16, top: 18, bottom: 46 },
    tooltip: {
      formatter: (params: { data: number[] }) =>
        `周${['一', '二', '三', '四', '五', '六', '日'][params.data[1]]} ${params.data[0]}:00<br/>得分 ${params.data[2]}`,
    },
    xAxis: {
      type: 'category',
      data: Array.from({ length: 24 }, (_, index) => `${index}`),
      axisLabel: { interval: 1, fontSize: 9 },
      splitArea: { show: true },
    },
    yAxis: {
      type: 'category',
      data: ['周一', '周二', '周三', '周四', '周五', '周六', '周日'],
      axisLabel: { fontSize: 10 },
      splitArea: { show: true },
    },
    visualMap: {
      min: 0,
      max,
      calculable: false,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      itemHeight: 70,
      textStyle: { fontSize: 9 },
      inRange: { color: ['#eef2ff', '#93b4fd', '#2563EB'] },
    },
    series: [
      {
        type: 'heatmap',
        data: rows.map((item) => [item.hour, item.dayOfWeek, item.score]),
        progressive: 0,
      },
    ],
  }
})
async function loadAnalysis() {
  if (
    analysisFilter.value.window === 'CUSTOM' &&
    (!analysisFilter.value.start_date || !analysisFilter.value.end_date)
  ) {
    return ElMessage.warning('自定义时间范围需要填写开始和结束日期')
  }
  analysisLoading.value = true
  try {
    const params: Record<string, unknown> = {
      source_scope: analysisFilter.value.source_scope,
      window: analysisFilter.value.window,
    }
    if (analysisFilter.value.platform) params.platform = analysisFilter.value.platform
    if (analysisFilter.value.account_id) params.account_id = analysisFilter.value.account_id
    if (analysisFilter.value.content_type) params.content_type = analysisFilter.value.content_type
    if (analysisFilter.value.window === 'CUSTOM') {
      params.start_date = analysisFilter.value.start_date
      params.end_date = analysisFilter.value.end_date
    }
    analysis.value = await workflowApi.activityAnalysis(params)
  } catch (e) {
    ElMessage.error(getApiErrorMessage(e))
  } finally {
    analysisLoading.value = false
  }
}

/* ---------- 历史数据导入 ---------- */
const importForm = ref<{
  default_platform: Platform | ''
  default_source_type: string
  default_content_type: string
  source_note: string
}>({
  default_platform: '',
  default_source_type: 'ACCOUNT_HISTORY',
  default_content_type: '',
  source_note: '',
})
const sourceTypes = ref<Array<{ value: string; label: string }>>([])
type UploadFile = UploadRequestOptions['file']
const preview = ref<HistoryImportPreview>()
const previewFile = ref<UploadFile>()
const mapping = ref<Record<string, string>>({})
const importing = ref(false)
const batches = ref<HistoryImportBatch[]>([])
const totalRecords = ref(0)
const bySource = ref<Array<{ sourceType: string; label: string; count: number }>>([])

function buildFormData(file: UploadFile): FormData {
  const data = new FormData()
  data.append('file', file)
  data.append('mapping', JSON.stringify(mapping.value))
  data.append('default_platform', importForm.value.default_platform)
  data.append('default_source_type', importForm.value.default_source_type)
  data.append('default_content_type', importForm.value.default_content_type)
  data.append('source_note', importForm.value.source_note || '')
  return data
}
async function handleUpload(options: UploadRequestOptions) {
  const file = options.file
  previewFile.value = file
  mapping.value = {}
  try {
    preview.value = await workflowApi.previewHistoryImport(buildFormData(file))
    mapping.value = { ...preview.value.mapping }
    sourceTypes.value = preview.value.sourceTypes
    ElMessage.success(`解析完成，可导入 ${preview.value.importableRows} 行`)
  } catch (e) {
    preview.value = undefined
    ElMessage.error(getApiErrorMessage(e))
  }
}
async function reparse() {
  if (!previewFile.value) return
  try {
    preview.value = await workflowApi.previewHistoryImport(buildFormData(previewFile.value))
  } catch (e) {
    ElMessage.error(getApiErrorMessage(e))
  }
}
async function confirmImport() {
  if (!previewFile.value) return ElMessage.warning('请先上传文件')
  importing.value = true
  try {
    const batch = await workflowApi.importHistory(buildFormData(previewFile.value))
    ElMessage.success(
      `导入完成：成功 ${batch.successCount} 行，重复 ${batch.duplicateCount} 行，失败 ${batch.errorCount} 行`,
    )
    preview.value = undefined
    previewFile.value = undefined
    await loadBatches()
    await loadAnalysis()
  } catch (e) {
    ElMessage.error(getApiErrorMessage(e))
  } finally {
    importing.value = false
  }
}
async function loadBatches() {
  const data = await workflowApi.historyBatches()
  batches.value = data.items
  totalRecords.value = data.totalRecords
  bySource.value = data.bySource
}
async function removeBatch(row: HistoryImportBatch) {
  await ElMessageBox.confirm(
    `删除批次「${row.filename}」会同时移除该批次导入的历史数据，确定继续？`,
    '删除导入批次',
    { type: 'warning' },
  )
  try {
    const data = await workflowApi.deleteHistoryBatch(row.id)
    ElMessage.success(`已删除 ${data.removed} 条历史数据`)
    await loadBatches()
    await loadAnalysis()
  } catch (e) {
    ElMessage.error(getApiErrorMessage(e))
  }
}

onBeforeUnmount(() => stopCalcProgress())

onMounted(async () => {
  await loadArticles()
  contentTypes.value = await workflowApi.activityContentTypes()
  await Promise.all([loadAnalysis(), loadBatches()])
})
</script>
<template>
  <div>
    <PageHeader
      title="发布时间推荐"
      description="活跃度分析与时间推荐中心：导入历史数据 → 统计活跃时段 → 计算推荐发布时间。"
      ><el-button v-if="tab === 'recommend'" type="primary" :loading="loading" @click="calculate"
        ><Gauge :size="16" class="mr-2" />计算推荐时间</el-button
      ><el-button v-else-if="tab === 'activity'" :loading="analysisLoading" @click="loadAnalysis"
        ><Sparkles :size="16" class="mr-2" />刷新分析</el-button
      ><el-button v-else @click="workflowApi.downloadHistoryTemplate()"
        ><Download :size="16" class="mr-2" />下载导入模板</el-button
      ></PageHeader
    >
    <el-tabs v-model="tab" class="recommendation-tabs">
      <el-tab-pane v-if="canOperate" label="发布时间推荐" name="recommend" />
      <el-tab-pane label="活跃度分析" name="activity" />
      <el-tab-pane v-if="canOperate" label="历史数据" name="history" />
    </el-tabs>

    <template v-if="tab === 'recommend'">
      <section class="recommendation-toolbar">
        <label class="field-label"
          >内容<el-select v-model="articleId" filterable class="mt-2 w-full" @change="loadVariants"
            ><el-option
              v-for="item in articles"
              :key="item.id"
              :label="item.title"
              :value="item.id" /></el-select></label
        ><label class="field-label"
          >平台<el-segmented
            v-model="platform"
            :options="Object.entries(platformNames).map(([value, label]) => ({ value, label }))"
            class="mt-2 w-full"
            @change="accountId = undefined" /></label
        ><label class="field-label"
          >账号（可选）<el-select
            v-model="accountId"
            clearable
            class="mt-2 w-full"
            placeholder="按账号历史修正"
            ><el-option
              v-for="account in platformAccounts"
              :key="account.id!"
              :label="account.accountName"
              :value="account.id!" /></el-select
        ></label
        ><label class="field-label"
          >历史数据范围<el-select v-model="recommendWindow" class="mt-2 w-full"
            ><el-option
              v-for="item in timeWindowOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value" /></el-select></label
        ><template v-if="recommendWindow === 'CUSTOM'"
          ><label class="field-label"
            >开始日期<el-date-picker
              v-model="recommendStartDate"
              type="date"
              value-format="YYYY-MM-DD"
              class="mt-2 w-full" /></label
          ><label class="field-label"
            >结束日期<el-date-picker
              v-model="recommendEndDate"
              type="date"
              value-format="YYYY-MM-DD"
              class="mt-2 w-full" /></label
        ></template>
      </section>
      <template v-if="loading"
        ><section class="recommend-progress">
          <div class="recommend-progress-head">
            <strong>正在计算推荐时间</strong>
            <span>{{ calcPercent }}%</span>
          </div>
          <div class="recommend-progress-bar">
            <i :style="{ width: `${calcPercent}%` }" />
          </div>
          <ol>
            <li
              v-for="(step, index) in CALC_STEPS"
              :key="step"
              :class="{
                done: index < calcStep || calcPercent >= 100,
                current: index === calcStep && calcPercent < 100,
              }"
            >
              <em>{{ index < calcStep || calcPercent >= 100 ? '✓' : index + 1 }}</em>
              <span>{{ step }}</span>
            </li>
          </ol>
        </section></template
      >
      <template v-else-if="result"
        ><section class="recommendation-layout">
          <article class="recommendation-curve">
            <header>
              <h2>24 小时活跃曲线</h2>
              <span>{{
                new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric' })
              }}</span>
            </header>
            <ChartPanel :option="option" height="360px" />
            <p class="curve-note">
              {{ result.dataSource.baseline }} · {{ result.dataSource.accountHistory }} ·
              {{ result.dataSufficiency.message }}
              <template v-if="result.window">
                · 分析范围：{{ result.window.label }}
                <template v-if="result.window.startDate"
                  >（{{ result.window.startDate }} ~ {{ result.window.endDate }}）</template
                >
              </template>
            </p>
          </article>
          <aside class="recommendation-result">
            <p>最佳时间</p>
            <div class="best-time">
              <span class="icon-tile"><Clock3 :size="21" /></span>
              <div>
                <strong>
                  {{
                    new Date(result.recommendedAt).toLocaleString('zh-CN', {
                      month: '2-digit',
                      day: '2-digit',
                      hour: '2-digit',
                      minute: '2-digit',
                    })
                  }}
                </strong>
                <span
                  >推荐得分 {{ result.score }} · 置信度
                  {{ confidenceLabels[result.confidence] || result.confidence }} ·
                  {{ result.contentTypeName }}</span
                >
              </div>
            </div>
            <div v-if="isColdStart" class="cold-start-card">
              <p>
                当前是<strong>冷启动推荐</strong>：账号历史为 0，公开导入样本也为 0。今晚
                {{
                  new Date(result.recommendedAt).toLocaleTimeString('zh-CN', {
                    hour: '2-digit',
                    minute: '2-digit',
                  })
                }}
                主要依据
                <strong>平台人工时段规则</strong>（{{ result.dataSource.priorRuleCount }} 条）+
                内容类型 + 读者作息，不是根据你账号的真实历史算出来的。
              </p>
              <p>要提高可信度：切到「历史数据」导入该平台账号历史，或把时间范围改为「全部时间」。</p>
            </div>
            <p v-if="result.narrative" class="advisor-narrative">
              <Sparkles :size="14" />{{ result.narrative }}
              <small>{{ result.narrativeProvider === 'LLM' ? '大模型整理' : '规则生成' }}</small>
            </p>
            <div v-if="result.warnings.length" class="advisor-warnings">
              <p v-for="item in result.warnings" :key="item">
                <TriangleAlert :size="13" />{{ item }}
              </p>
            </div>
            <div v-if="result.window && !result.window.sufficient" class="advisor-warnings">
              <p><TriangleAlert :size="13" />{{ result.window.message }}</p>
            </div>
            <div class="recommendation-reasons">
              <h3>推荐理由</h3>
              <div v-for="reason in result.reasons" :key="reason.type" class="reason-card">
                <Lightbulb :size="16" />
                <div>
                  <p>{{ reason.description }}</p>
                  <small>贡献 {{ reason.contribution }} 分</small>
                </div>
              </div>
            </div>
            <div class="alternative-times">
              <p>备选时间</p>
              <div>
                <span
                  v-for="item in result.alternatives"
                  :key="item.recommendedAt"
                  class="meta-chip"
                  >{{
                    new Date(item.recommendedAt).toLocaleString('zh-CN', {
                      month: '2-digit',
                      day: '2-digit',
                      hour: '2-digit',
                      minute: '2-digit',
                    })
                  }}
                  · {{ item.score }}</span
                >
              </div>
            </div>
            <div class="alternative-times">
              <p>样本与来源</p>
              <div>
                <span class="meta-chip">账号历史 {{ result.accountSampleCount }} 条</span>
                <span class="meta-chip">公开导入样本 {{ result.baselineSampleCount }} 条</span>
                <span class="meta-chip"
                  >人工时段规则 {{ result.dataSource.priorRuleCount }} 条</span
                >
                <span
                  v-for="item in result.dataSource.sourceTypes"
                  :key="item.sourceType"
                  class="meta-chip"
                  >{{ item.label }} · {{ item.count }}</span
                >
              </div>
              <p v-if="isColdStart" class="source-hint">
                「公开导入样本 0」不等于没有依据：曲线和得分仍可来自人工维护的平台时段规则。
              </p>
            </div>
          </aside>
        </section></template
      >
      <div v-else class="empty-state recommendation-empty">
        <CalendarPlus :size="24" />
        <p>选择内容，计算发布时间</p>
      </div>
    </template>

    <template v-else-if="tab === 'activity'">
      <section class="recommendation-toolbar activity-toolbar">
        <label class="field-label"
          >平台<el-select
            v-model="analysisFilter.platform"
            clearable
            class="mt-2 w-full"
            placeholder="全部平台"
            @change="loadAnalysis"
            ><el-option
              v-for="(name, key) in analysisPlatformNames"
              :key="key"
              :label="name"
              :value="key" /></el-select></label
        ><label class="field-label"
          >账号<el-select
            v-model="analysisFilter.account_id"
            clearable
            class="mt-2 w-full"
            placeholder="全部账号"
            @change="loadAnalysis"
            ><el-option
              v-for="account in analysisAccounts"
              :key="account.id!"
              :label="account.accountName"
              :value="account.id!" /></el-select></label
        ><label class="field-label"
          >内容类型<el-select
            v-model="analysisFilter.content_type"
            clearable
            class="mt-2 w-full"
            placeholder="全部类型"
            @change="loadAnalysis"
            ><el-option
              v-for="item in contentTypes"
              :key="item.value"
              :label="item.label"
              :value="item.value" /></el-select></label
        ><label class="field-label"
          >数据范围<el-select
            v-model="analysisFilter.source_scope"
            class="mt-2 w-full"
            @change="loadAnalysis"
            ><el-option label="全部数据" value="ALL" /><el-option
              label="仅账号历史"
              value="ACCOUNT" /><el-option label="仅公开基线" value="BASELINE"
          /></el-select>
        </label
        ><label class="field-label"
          >时间范围<el-select v-model="analysisFilter.window" class="mt-2 w-full" @change="loadAnalysis"
            ><el-option
              v-for="item in timeWindowOptions"
              :key="item.value"
              :label="item.label"
              :value="item.value" /></el-select></label
        ><template v-if="analysisFilter.window === 'CUSTOM'"
          ><label class="field-label"
            >开始日期<el-date-picker
              v-model="analysisFilter.start_date"
              type="date"
              value-format="YYYY-MM-DD"
              class="mt-2 w-full"
              @change="loadAnalysis" /></label
          ><label class="field-label"
            >结束日期<el-date-picker
              v-model="analysisFilter.end_date"
              type="date"
              value-format="YYYY-MM-DD"
              class="mt-2 w-full"
              @change="loadAnalysis" /></label
        ></template>
      </section>
      <template v-if="analysis">
        <section v-if="analysis.windowInfo" class="notice-strip">
          <Gauge :size="16" /><span
            >{{ analysis.windowInfo.label }}
            <template v-if="analysis.windowInfo.startDate"
              >（{{ analysis.windowInfo.startDate }} ~ {{ analysis.windowInfo.endDate }}）</template
            >
            · {{ analysis.windowInfo.message }}</span
          >
        </section>
        <template v-if="analysis.sampleCount">
        <section class="activity-metrics">
          <article>
            <span>样本总数</span><b>{{ analysis.sampleCount }}</b>
          </article>
          <article>
            <span>账号历史</span><b>{{ analysis.accountSampleCount }}</b>
          </article>
          <article>
            <span>公开基线</span><b>{{ analysis.baselineSampleCount }}</b>
          </article>
          <article>
            <span>数据完整度</span><b>{{ analysis.completeness.score }}%</b>
          </article>
        </section>
        <section class="activity-grid">
          <article class="panel-card">
            <header><h3>星期活跃度</h3></header>
            <ChartPanel :option="weekdayOption" height="230px" />
          </article>
          <article class="panel-card">
            <header><h3>24 小时活跃度</h3></header>
            <ChartPanel :option="hourlyOption" height="230px" />
          </article>
        </section>
        <section class="panel-card">
          <header><h3>星期 × 小时分布</h3></header>
          <ChartPanel :option="heatmapOption" height="300px" />
        </section>
        <section class="activity-grid">
          <article class="panel-card">
            <header><h3>最佳时段 Top 8</h3></header>
            <ul class="slot-list">
              <li v-for="item in analysis.topSlots" :key="`${item.dayOfWeek}-${item.hour}`">
                <b>{{ item.dayName }} {{ item.time }}</b>
                <span>得分 {{ item.score }} · 样本 {{ item.sampleCount }}</span>
              </li>
            </ul>
          </article>
          <article class="panel-card">
            <header><h3>内容类型最佳时段</h3></header>
            <ul class="slot-list">
              <li v-for="item in analysis.contentTypes" :key="item.contentType">
                <b>{{ item.contentTypeName }}</b>
                <span>
                  {{
                    item.bestSlots.map((slot) => `${slot.dayName} ${slot.time}`).join(' / ') || '—'
                  }}
                  · 样本 {{ item.sampleCount }}
                </span>
              </li>
            </ul>
          </article>
        </section>
        <section class="panel-card">
          <header><h3>数据完整度</h3></header>
          <div class="completeness-grid">
            <div v-for="item in analysis.completeness.fields" :key="item.field">
              <span>{{ item.label }}</span>
              <i><em :style="{ width: `${item.percent}%` }" /></i>
              <b>{{ item.percent }}%</b>
            </div>
          </div>
          <p class="panel-note">{{ analysis.scoreFormula }}</p>
          <p class="panel-note">{{ analysis.notice }}</p>
        </section>
        </template>
        <div v-else class="empty-state recommendation-empty">
          <Database :size="24" />
          <p>所选时间范围内暂无历史数据，请扩大时间范围或在「历史数据导入」页签补充数据。</p>
        </div>
      </template>
      <div v-else-if="!analysisLoading" class="empty-state recommendation-empty">
        <Database :size="24" />
        <p>还没有历史数据。请在「历史数据导入」页签导入 CSV / Excel 后再查看活跃度分析。</p>
      </div>
    </template>

    <template v-else>
      <section class="activity-metrics">
        <article>
          <span>历史记录总数</span><b>{{ totalRecords }}</b>
        </article>
        <article v-for="item in bySource" :key="item.sourceType">
          <span>{{ item.label }}</span
          ><b>{{ item.count }}</b>
        </article>
      </section>
      <section v-if="canOperate" class="panel-card">
        <header><h3>导入历史互动数据</h3></header>
        <div class="import-form">
          <label class="field-label"
            >默认平台<el-select
              v-model="importForm.default_platform"
              clearable
              class="mt-2 w-full"
              placeholder="文件内含 platform 列时可留空"
              ><el-option
                v-for="(name, key) in platformNames"
                :key="key"
                :label="name"
                :value="key" /></el-select></label
          ><label class="field-label"
            >数据来源<el-select v-model="importForm.default_source_type" class="mt-2 w-full"
              ><el-option
                v-for="item in sourceTypes.length
                  ? sourceTypes
                  : [
                      { value: 'ACCOUNT_HISTORY', label: '账号历史数据' },
                      { value: 'PUBLIC_DATASET', label: '公开数据集' },
                      { value: 'YOUTUBE_PUBLIC', label: 'YouTube 公开样本' },
                      { value: 'SIMULATED', label: '模拟样本（SIMULATED）' },
                    ]"
                :key="item.value"
                :label="item.label"
                :value="item.value" /></el-select></label
          ><label class="field-label"
            >默认内容类型<el-select
              v-model="importForm.default_content_type"
              clearable
              class="mt-2 w-full"
              placeholder="文件内含 content_type 列时可留空"
              ><el-option
                v-for="item in contentTypes"
                :key="item.value"
                :label="item.label"
                :value="item.value" /></el-select></label
          ><label class="field-label"
            >来源备注<el-input
              v-model="importForm.source_note"
              class="mt-2"
              placeholder="例如：YouTubeDurationData 公开样本"
          /></label>
        </div>
        <el-upload
          class="import-upload"
          drag
          :show-file-list="false"
          accept=".csv,.xlsx,.xls"
          :http-request="handleUpload"
        >
          <Upload :size="22" />
          <p>点击或拖拽上传 CSV / Excel</p>
          <small
            >支持
            platform、account_id、content_type、publish_time、views、impressions、likes、comments、shares、favorites、followers、source_type</small
          >
        </el-upload>
        <template v-if="preview">
          <div class="import-stats">
            <span>共 {{ preview.totalRows }} 行</span
            ><span>可导入 {{ preview.importableRows }}</span
            ><span>格式错误 {{ preview.errorRows }}</span
            ><span>文件内重复 {{ preview.duplicateInFile }}</span
            ><span>与已有重复 {{ preview.duplicateInDatabase }}</span
            ><span>缺失值 {{ preview.missingValueRows }}</span>
          </div>
          <div class="mapping-grid">
            <label v-for="field in preview.fields" :key="field.field">
              <span>{{ field.label }}<i v-if="field.required">*</i></span>
              <el-select
                v-model="mapping[field.field]"
                size="small"
                clearable
                placeholder="未映射"
                @change="reparse"
              >
                <el-option
                  v-for="header in preview.headers"
                  :key="header"
                  :label="header"
                  :value="header"
                />
              </el-select>
            </label>
          </div>
          <el-table :data="preview.preview" size="small" max-height="260" class="mt-3">
            <el-table-column prop="row" label="行号" width="70" />
            <el-table-column prop="platform" label="平台" width="120" />
            <el-table-column prop="accountRef" label="账号" width="120" />
            <el-table-column prop="contentTypeName" label="内容类型" width="110" />
            <el-table-column prop="publishTime" label="发布时间" width="170" />
            <el-table-column prop="views" label="浏览" width="80" />
            <el-table-column prop="likes" label="点赞" width="80" />
            <el-table-column prop="comments" label="评论" width="80" />
            <el-table-column prop="shares" label="分享" width="80" />
            <el-table-column prop="status" label="状态" width="100" />
          </el-table>
          <div v-if="preview.errors.length" class="import-errors">
            <p v-for="item in preview.errors" :key="item.row">
              <TriangleAlert :size="12" />第 {{ item.row }} 行：{{ item.message }}
            </p>
          </div>
          <el-button
            type="primary"
            class="mt-3"
            :loading="importing"
            :disabled="!preview.importableRows"
            @click="confirmImport"
            >确认导入 {{ preview.importableRows }} 行</el-button
          >
        </template>
      </section>
      <section class="panel-card">
        <header><h3>导入批次</h3></header>
        <el-table :data="batches" size="small">
          <el-table-column prop="filename" label="文件" min-width="180" />
          <el-table-column prop="sourceLabel" label="数据来源" width="140" />
          <el-table-column prop="totalRows" label="总行数" width="90" />
          <el-table-column prop="successCount" label="成功" width="80" />
          <el-table-column prop="duplicateCount" label="重复" width="80" />
          <el-table-column prop="errorCount" label="失败" width="80" />
          <el-table-column prop="remainingRows" label="当前保留" width="90" />
          <el-table-column label="导入时间" width="170"
            ><template #default="{ row }">{{
              new Date(row.createdAt).toLocaleString('zh-CN')
            }}</template></el-table-column
          >
          <el-table-column v-if="canOperate" label="操作" width="90"
            ><template #default="{ row }"
              ><el-button link type="danger" @click="removeBatch(row)">删除</el-button></template
            ></el-table-column
          >
        </el-table>
        <p class="panel-note">
          公开样本（含 YouTube 公开数据集）只作为冷启动基线，系统不会把它展示为微博 / 小红书 /
          微信公众号的真实平台数据。
        </p>
      </section>
    </template>
  </div>
</template>
