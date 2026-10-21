<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UploadRequestOptions } from 'element-plus'
import { Check, Database, Download, Gauge, Sparkles, TriangleAlert, Upload } from 'lucide-vue-next'
import PageHeader from '@/components/PageHeader.vue'
import ChartPanel from '@/components/ChartPanel.vue'
import RecommendationTargetForm from '@/components/recommendation/RecommendationTargetForm.vue'
import RecommendationResultTable from '@/components/recommendation/RecommendationResultTable.vue'
import RecommendationDetailDrawer from '@/components/recommendation/RecommendationDetailDrawer.vue'
import ContentScheduleProfilePanel from '@/components/recommendation/ContentScheduleProfilePanel.vue'
import BatchScheduleConfirm from '@/components/recommendation/BatchScheduleConfirm.vue'
import { RECOMMEND_PLATFORMS, useBatchRecommendation } from '@/composables/useBatchRecommendation'
import { workflowApi } from '@/api/workflow'
import { getApiErrorMessage } from '@/api/client'
import { fallbackHistorySources, historyInputSources } from '@/utils/historySources'
import { useAuthStore } from '@/stores/auth'
import type {
  ActivityAnalysis,
  HistoryImportBatch,
  HistoryImportPreview,
  Platform,
  RecommendationPlanRow,
  TimeWindow,
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
const tab = ref<'recommend' | 'activity' | 'history'>(canOperate.value ? 'recommend' : 'activity')
const batch = useBatchRecommendation()
const detailRow = ref<RecommendationPlanRow>()
const detailOpen = ref(false)
const confirmOpen = ref(false)
const staggerMinutes = ref(15)

/* ---------- 活跃度分析 / 历史数据（保留原能力） ---------- */
const analysis = ref<ActivityAnalysis>()
let analysisSequence = 0
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
  batch.accounts.value.filter(
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
  const sequence = ++analysisSequence
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
    const data = await workflowApi.activityAnalysis(params)
    if (sequence !== analysisSequence) return
    analysis.value = data
  } catch (e) {
    if (sequence === analysisSequence) {
      analysis.value = undefined
      ElMessage.error(getApiErrorMessage(e))
    }
  } finally {
    if (sequence === analysisSequence) analysisLoading.value = false
  }
}

function onAnalysisPlatformChange() {
  analysisFilter.value.account_id = undefined
  void loadAnalysis()
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
const sourceTypes = ref([...fallbackHistorySources])

async function loadHistoryFields() {
  try {
    const metadata = await workflowApi.historyFields()
    sourceTypes.value = historyInputSources(metadata.sourceTypes)
  } catch {
    sourceTypes.value = [...fallbackHistorySources]
  }
}
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
    sourceTypes.value = historyInputSources(preview.value.sourceTypes)
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
    sourceTypes.value = historyInputSources(preview.value.sourceTypes)
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

onBeforeUnmount(() => batch.stopCalcProgress())

onMounted(async () => {
  const fieldsLoading = loadHistoryFields()
  await batch.loadArticles()
  contentTypes.value = batch.contentTypes.value
  await Promise.all([loadAnalysis(), loadBatches(), fieldsLoading])
})

function onPlatformsChange(platforms: Platform[]) {
  batch.selectedPlatforms.value = platforms
  batch.syncAccountDefaults()
}

function openDetail(row: RecommendationPlanRow) {
  detailRow.value = row
  detailOpen.value = true
}

async function confirmBatchSchedule() {
  await batch.createBatchSchedules()
  confirmOpen.value = false
}
</script>
<template>
  <div>
    <PageHeader
      title="发布时间推荐"
      description="跨平台排期中心：一次计算多平台推荐时间，确认后批量写入日历排期。"
    >
      <el-button v-if="tab === 'activity'" :loading="analysisLoading" @click="loadAnalysis">
        <Sparkles :size="16" class="mr-2" />刷新分析
      </el-button>
      <el-button v-else-if="tab === 'history'" @click="workflowApi.downloadHistoryTemplate()">
        <Download :size="16" class="mr-2" />下载导入模板
      </el-button>
    </PageHeader>
    <el-tabs v-model="tab" class="recommendation-tabs">
      <el-tab-pane v-if="canOperate" label="跨平台排期" name="recommend" />
      <el-tab-pane label="活跃度分析" name="activity" />
      <el-tab-pane v-if="canOperate" label="历史数据" name="history" />
    </el-tabs>

    <template v-if="tab === 'recommend'">
      <RecommendationTargetForm
        :articles="batch.articles.value"
        :article-id="batch.articleId.value"
        :selected-platforms="batch.selectedPlatforms.value"
        :content-type="batch.contentType.value"
        :content-types="batch.contentTypes.value"
        :recommend-window="batch.recommendWindow.value"
        :recommend-start-date="batch.recommendStartDate.value"
        :recommend-end-date="batch.recommendEndDate.value"
        :can-calculate="batch.canCalculate.value"
        :calculate-hint="batch.calculateHint.value"
        :loading="batch.loading.value"
        :platform-options="RECOMMEND_PLATFORMS"
        :time-window-options="timeWindowOptions"
        :account-by-platform="batch.accountByPlatform"
        :accounts-for="batch.accountsFor"
        @update:article-id="batch.articleId.value = $event"
        @update:selected-platforms="onPlatformsChange"
        @update:content-type="batch.contentType.value = $event"
        @update:recommend-window="batch.recommendWindow.value = $event"
        @update:recommend-start-date="batch.recommendStartDate.value = $event"
        @update:recommend-end-date="batch.recommendEndDate.value = $event"
        @update:account="(platform, accountId) => (batch.accountByPlatform[platform] = accountId)"
        @article-change="batch.loadVariants()"
        @calculate="batch.calculateBatch()"
      />

      <section class="pipeline-switch mt-3">
        <el-switch v-model="batch.optimizeEnabled.value" size="small" />
        <div>
          <strong>智能联合排期</strong>
          <span>
            结合内容特点、历史表现和账号活跃时间，统筹各平台排期。关闭后使用历史时段评分；智能分析暂不可用时，也会自动采用历史评分结果。
          </span>
        </div>
      </section>

      <section v-if="batch.loading.value" class="recommend-progress mt-3">
        <div class="recommend-progress-head">
          <strong>正在计算跨平台推荐</strong>
          <span>{{ batch.calcStep.value === 0 ? '等待服务响应' : '正在检查冲突' }}</span>
        </div>
        <p class="recommend-progress-note">
          正在计算推荐时间，随后会核对已有排期。完成后，结果会显示在下方。
        </p>
        <ol>
          <li
            v-for="(step, index) in batch.CALC_STEPS"
            :key="step"
            :class="{
              done: index < batch.calcStep.value || batch.calcPercent.value >= 100,
              current: index === batch.calcStep.value && batch.calcPercent.value < 100,
            }"
          >
            <em>
              <Check
                v-if="index < batch.calcStep.value || batch.calcPercent.value >= 100"
                :size="13"
                aria-label="已完成"
              />
              <template v-else>{{ index + 1 }}</template>
            </em>
            <span>{{ step }}</span>
          </li>
        </ol>
      </section>

      <template v-else-if="batch.planRows.value.length">
        <ContentScheduleProfilePanel
          v-if="batch.plan.value"
          class="mt-3"
          :profile="batch.plan.value.profile"
          :profile-source="batch.plan.value.profileSource"
          :plan="batch.plan.value"
        />

        <div v-if="batch.batchResult.value?.hasOverlap" class="overlap-banner mt-3">
          <p>
            多个平台推荐时间重合：
            {{
              batch.batchResult.value?.overlapGroups
                .map((group) => group.map((p) => platformNames[p]).join('、'))
                .join('；')
            }}
          </p>
          <div class="overlap-actions">
            <el-select v-model="staggerMinutes" class="!w-28" size="small">
              <el-option label="错开 15 分钟" :value="15" />
              <el-option label="错开 30 分钟" :value="30" />
            </el-select>
            <el-button size="small" @click="batch.staggerOverlaps(staggerMinutes)"
              >一键错开</el-button
            >
          </div>
        </div>

        <RecommendationResultTable
          class="mt-3"
          :rows="batch.planRows.value"
          :confidence-labels="batch.confidenceLabels"
          @best="batch.applyBestTime"
          @alternative="batch.applyAlternative"
          @custom="batch.applyCustomTime"
          @skip="batch.toggleSkip"
          @lock="batch.toggleLock"
          @detail="openDetail"
        />

        <div class="batch-actions mt-3">
          <el-button
            type="primary"
            :disabled="!batch.canSchedule.value"
            @click="confirmOpen = true"
          >
            一键生成跨平台排期
          </el-button>
          <span v-if="!batch.canSchedule.value" class="form-hint"
            >请至少保留一个平台并确认排期时间</span
          >
        </div>
      </template>

      <section v-else-if="batch.lastError.value" class="calc-error mt-3">
        <TriangleAlert :size="18" />
        <div>
          <strong>计算未产出结果</strong>
          <p>{{ batch.lastError.value }}</p>
          <p class="calc-error-hint">
            智能分析可能需要较长时间。可稍后重试，或关闭“智能联合排期”，使用历史评分计算。
          </p>
        </div>
        <el-button type="primary" @click="batch.calculateBatch()">重新计算</el-button>
      </section>

      <section v-else class="guide-steps mt-3">
        <h3>三步完成跨平台排期</h3>
        <ol>
          <li><strong>1. 选择内容</strong><span>从内容库挑选待排期文章</span></li>
          <li><strong>2. 选择平台和账号</strong><span>多选目标平台，并为每个平台指定账号</span></li>
          <li>
            <strong>3. 计算推荐并生成排期</strong
            ><span>结果会出现在下方表格；点「详情」可看画像、相似历史与调整原因</span>
          </li>
        </ol>
      </section>

      <RecommendationDetailDrawer
        v-model="detailOpen"
        :row="detailRow"
        :confidence-labels="batch.confidenceLabels"
      />
      <BatchScheduleConfirm
        v-model="confirmOpen"
        :rows="batch.activePlanRows.value"
        :scheduling="batch.scheduling.value"
        @confirm="confirmBatchSchedule"
      />
    </template>

    <template v-else-if="tab === 'activity'">
      <section class="recommendation-toolbar activity-toolbar">
        <label class="field-label"
          >平台<el-select
            v-model="analysisFilter.platform"
            clearable
            class="mt-2 w-full"
            placeholder="全部平台"
            @change="onAnalysisPlatformChange"
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
          /></el-select> </label
        ><label class="field-label"
          >时间范围<el-select
            v-model="analysisFilter.window"
            class="mt-2 w-full"
            @change="loadAnalysis"
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
              >（{{ analysis.windowInfo.startDate }} 至
              {{ analysis.windowInfo.endDate }}）</template
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
            <header><h3>每周活跃时间分布</h3></header>
            <ChartPanel :option="heatmapOption" height="300px" />
          </section>
          <section class="activity-grid">
            <article class="panel-card">
              <header><h3>推荐时段前八名</h3></header>
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
                      item.bestSlots.map((slot) => `${slot.dayName} ${slot.time}`).join('、') ||
                      '暂无推荐时段'
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
              placeholder="文件已包含平台时可留空"
              ><el-option
                v-for="(name, key) in platformNames"
                :key="key"
                :label="name"
                :value="key" /></el-select></label
          ><label class="field-label"
            >数据来源<el-select
              v-model="importForm.default_source_type"
              data-testid="history-import-source"
              class="mt-2 w-full"
              ><el-option
                v-for="item in sourceTypes"
                :key="item.value"
                :label="item.label"
                :value="item.value" /></el-select></label
          ><label class="field-label"
            >默认内容类型<el-select
              v-model="importForm.default_content_type"
              clearable
              class="mt-2 w-full"
              placeholder="文件已包含内容类型时可留空"
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
          <small>支持平台、账号、内容类型、发布时间和互动指标，上传后可选择对应列。</small>
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
            <el-table-column label="平台" width="120">
              <template #default="{ row }">{{
                platformNames[row.platform as Platform] || '其他平台'
              }}</template>
            </el-table-column>
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

<style scoped>
.guide-steps {
  border: 1px dashed var(--sf-line, #e5e7eb);
  border-radius: 10px;
  background: #fafbfc;
  padding: 16px 18px;
}
.guide-steps h3 {
  margin: 0 0 10px;
  font-size: 14px;
  font-weight: 600;
}
.guide-steps ol {
  margin: 0;
  padding-left: 0;
  list-style: none;
  display: grid;
  gap: 10px;
}
.guide-steps li strong {
  display: block;
  color: var(--sf-ink, #172033);
  font-size: 13px;
}
.guide-steps li span {
  color: var(--sf-muted, #667085);
  font-size: 12px;
}
.pipeline-switch {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  border: 1px solid var(--sf-line, #e5e7eb);
  border-radius: 10px;
  background: #fff;
  padding: 10px 12px;
}
.pipeline-switch strong {
  display: block;
  color: var(--sf-ink, #172033);
  font-size: 12px;
  font-weight: 600;
}
.pipeline-switch span {
  display: block;
  margin-top: 2px;
  color: var(--sf-muted, #667085);
  font-size: 12px;
  line-height: 1.6;
}
.calc-error {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  border: 1px solid #fecdca;
  border-radius: 10px;
  background: #fef3f2;
  padding: 14px 16px;
  color: #b42318;
}
.calc-error strong {
  display: block;
  font-size: 13px;
}
.calc-error p {
  margin: 4px 0 0;
  font-size: 12px;
  line-height: 1.6;
}
.calc-error-hint {
  color: #912018 !important;
}
.calc-error .el-button {
  margin-left: auto;
  flex-shrink: 0;
}
.recommend-progress-note {
  margin: 0 0 10px;
  color: var(--sf-muted, #667085);
  font-size: 12px;
  line-height: 1.5;
}
.overlap-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border: 1px solid #fedf89;
  border-radius: 8px;
  background: #fffaeb;
  padding: 10px 12px;
}
.overlap-banner p {
  margin: 0;
  color: #b54708;
  font-size: 12px;
}
.overlap-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.batch-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
.form-hint {
  color: #b54708;
  font-size: 12px;
}
</style>
