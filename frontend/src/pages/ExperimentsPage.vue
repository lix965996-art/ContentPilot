<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Beaker, Play, Plus } from 'lucide-vue-next'
import PageHeader from '@/components/PageHeader.vue'
import EmptyState from '@/components/EmptyState.vue'
import { workflowApi } from '@/api/workflow'
import { getApiErrorMessage } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import type { ExperimentSampleRow } from '@/types/business'
const auth = useAuthStore()
const canOperate = computed(() => auth.canManageBusiness)
const rows = ref<Array<Record<string, any>>>([])
const dialog = ref(false)
const detail = ref<Record<string, any>>()
const drawer = ref(false)
const form = reactive({
  name: '',
  type: 'PUBLISH_TIME',
  hypothesis: '',
  control_description: '',
  treatment_description: '',
  metrics: {} as Record<string, string>,
})
const controlStats = computed(() => detail.value?.statistics?.CONTROL || {})
const treatmentStats = computed(() => detail.value?.statistics?.TREATMENT || {})
const engagementDifference = computed(
  () =>
    Number(treatmentStats.value.engagementRate || 0) -
    Number(controlStats.value.engagementRate || 0),
)

function typeLabel(value: string) {
  return value === 'PUBLISH_TIME' ? '发布时间对比' : '内容效果对比'
}

function statusLabel(value: string) {
  if (['RUNNING', 'ACTIVE'].includes(value)) return '进行中'
  if (value === 'FINISHED') return '已结束'
  return '未开始'
}

function statusType(value: string) {
  if (['RUNNING', 'ACTIVE'].includes(value)) return 'success'
  if (value === 'FINISHED') return 'info'
  return 'warning'
}

function groupLabel(value: string) {
  return value === 'TREATMENT' ? '按推荐时间发' : '按平时时间发'
}

function formatPercent(value: unknown) {
  const number = Number(value)
  return Number.isFinite(number) ? `${number.toFixed(2)}%` : '暂无数据'
}

function formatDate(value: unknown) {
  return value ? new Date(String(value)).toLocaleDateString('zh-CN') : '—'
}

function conclusionText() {
  const controlCount = Number(controlStats.value.sampleCount || 0)
  const treatmentCount = Number(treatmentStats.value.sampleCount || 0)
  if (controlCount < 3 || treatmentCount < 3) {
    return '两组样本都不足 3 条，目前只能验证流程，不能据此调整正式发布时间。'
  }
  const difference = engagementDifference.value
  if (Math.abs(difference) < 0.5) return '两组互动率接近，暂未观察到明显差异。'
  return difference > 0
    ? `按推荐时间发的平均互动率高 ${difference.toFixed(2)} 个百分点。`
    : `按推荐时间发的平均互动率低 ${Math.abs(difference).toFixed(2)} 个百分点。`
}
const BACKTEST_EXPERIMENT_NAME = '公开样本发布时间历史回测实验'
const syncing = ref(false)
const overrideDialog = ref(false)
const overrideSample = ref<ExperimentSampleRow>()
const overrideForm = reactive({
  group_type: 'TREATMENT' as 'CONTROL' | 'TREATMENT',
  reason: '',
})

const featuredExperiment = computed(() =>
  rows.value.find((row) => row.name === BACKTEST_EXPERIMENT_NAME && row.status === 'FINISHED'),
)

const featuredDiff = computed(() => {
  const stats = featuredExperiment.value?.statistics
  if (!stats?.TREATMENT || !stats?.CONTROL) return null
  return Number(stats.TREATMENT.engagementRate || 0) - Number(stats.CONTROL.engagementRate || 0)
})

const otherExperiments = computed(() =>
  rows.value.filter((row) => row.name !== BACKTEST_EXPERIMENT_NAME),
)

function resultHeadline(row: Record<string, any>) {
  if (row.status !== 'FINISHED') return ''
  const treatment = row.statistics?.TREATMENT
  const control = row.statistics?.CONTROL
  if (!treatment?.sampleCount && !control?.sampleCount) return row.conclusion || ''
  const diff = Number(treatment?.engagementRate || 0) - Number(control?.engagementRate || 0)
  if (Math.abs(diff) < 0.05) return '两组互动率接近，差异不明显。'
  return diff > 0
    ? `按推荐时间发 ${Number(treatment?.engagementRate || 0).toFixed(2)}%，比平时时间高 ${Math.abs(diff).toFixed(2)} 个百分点。`
    : `按平时时间发更好，推荐时间低 ${Math.abs(diff).toFixed(2)} 个百分点。`
}

function dataSourceLabel(row: Record<string, any>) {
  if (row.result?.dataSource === 'YOUTUBE_PUBLIC_SAMPLE') return 'YouTube 公开样本'
  if (row.hasSimulatedData) return '本地演示'
  return '排期实测'
}
async function load() {
  rows.value = (await workflowApi.experiments()).sort((a, b) => {
    if (a.name === BACKTEST_EXPERIMENT_NAME) return -1
    if (b.name === BACKTEST_EXPERIMENT_NAME) return 1
    return 0
  })
}
async function create() {
  try {
    await workflowApi.createExperiment(form)
    dialog.value = false
    ElMessage.success('已创建')
    await load()
  } catch (e) {
    ElMessage.error(getApiErrorMessage(e))
  }
}
async function action(row: any, name: string) {
  await workflowApi.experimentAction(row.id, name)
  ElMessage.success(name === 'start' ? '已开始记录' : '对比已结束，两边结果已汇总')
  await load()
}
async function open(row: any) {
  detail.value = await workflowApi.experiment(row.id)
  drawer.value = true
}
async function syncSchedules(row: any) {
  syncing.value = true
  try {
    const data = await workflowApi.syncExperimentSchedules(row.id)
    ElMessage.success(`已自动同步 ${data.created} 条排期样本`)
    if (detail.value?.id === row.id) {
      detail.value = data.experiment
    }
    await load()
  } catch (e) {
    ElMessage.error(getApiErrorMessage(e))
  } finally {
    syncing.value = false
  }
}
function openOverride(sample: ExperimentSampleRow) {
  overrideSample.value = sample
  overrideForm.group_type = sample.groupType
  overrideForm.reason = sample.assignmentReason || ''
  overrideDialog.value = true
}
async function submitOverride() {
  if (!detail.value?.id || !overrideSample.value?.id) return
  if (!overrideForm.reason.trim()) return ElMessage.warning('请填写调整原因')
  try {
    detail.value = await workflowApi.overrideExperimentSampleGroup(
      detail.value.id,
      overrideSample.value.id,
      {
        group_type: overrideForm.group_type,
        reason: overrideForm.reason.trim(),
      },
    )
    overrideDialog.value = false
    ElMessage.success('分组已手动调整')
    await load()
  } catch (e) {
    ElMessage.error(getApiErrorMessage(e))
  }
}
function assignmentLabel(value?: string) {
  return value === 'MANUAL' ? '人工调整' : '自动分组'
}
onMounted(load)
</script>
<template>
  <div class="experiments-page">
    <PageHeader
      title="对比验证"
      description="把「按系统推荐时间发」和「按平时习惯发」分成两拨，看哪边互动更好。"
      ><el-button v-if="canOperate" type="primary" @click="dialog = true"
        ><Plus :size="16" class="mr-2" />新建对比</el-button
      ></PageHeader
    >

    <section v-if="featuredExperiment" class="hero-panel panel">
      <div class="hero-panel__head">
        <div>
          <p class="section-label">已用公开数据算过的结果</p>
          <h2 class="section-title mt-1">{{ featuredExperiment.name }}</h2>
        </div>
        <el-tag type="info" round>已结束</el-tag>
      </div>
      <div class="hero-panel__stats">
        <article>
          <span>按推荐时间发</span>
          <strong>{{
            formatPercent(featuredExperiment.statistics?.TREATMENT?.engagementRate)
          }}</strong>
          <small>{{ featuredExperiment.statistics?.TREATMENT?.sampleCount || 0 }} 条</small>
        </article>
        <article>
          <span>按平时时间发</span>
          <strong>{{
            formatPercent(featuredExperiment.statistics?.CONTROL?.engagementRate)
          }}</strong>
          <small>{{ featuredExperiment.statistics?.CONTROL?.sampleCount || 0 }} 条</small>
        </article>
        <article class="is-highlight">
          <span>差多少</span>
          <strong>{{
            featuredDiff !== null
              ? `${featuredDiff >= 0 ? '+' : ''}${featuredDiff.toFixed(2)}%`
              : '—'
          }}</strong>
          <small>YouTube 公开样本</small>
        </article>
      </div>
      <p class="hero-panel__note">{{ featuredExperiment.conclusion }}</p>
      <el-button type="primary" @click="open(featuredExperiment)">看明细</el-button>
    </section>

    <section class="mt-5">
      <div class="section-head">
        <h2 class="section-title">{{ canOperate ? '其他对比' : '全部对比' }}</h2>
        <span class="text-sm text-muted">{{ rows.length }} 个</span>
      </div>
      <div class="mt-3 grid gap-4 xl:grid-cols-2">
        <article v-for="row in otherExperiments" :key="row.id" class="experiment-card panel">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <p class="section-label">{{ typeLabel(row.type) }}</p>
                <span class="source-pill">{{ dataSourceLabel(row) }}</span>
              </div>
              <button
                class="mt-2 block w-full truncate text-left text-lg font-semibold text-ink hover:text-brand"
                @click="open(row)"
              >
                {{ row.name }}
              </button>
            </div>
            <el-tag :type="statusType(row.status)" round>{{ statusLabel(row.status) }}</el-tag>
          </div>
          <p v-if="resultHeadline(row)" class="experiment-result mt-4">{{ resultHeadline(row) }}</p>
          <p v-else class="mt-4 line-clamp-2 text-sm leading-6 text-muted">{{ row.hypothesis }}</p>
          <div class="experiment-footer">
            <span>{{ row.sampleCount }} 个样本</span>
            <div v-if="canOperate" class="experiment-actions">
              <el-button v-if="row.status === 'DRAFT'" type="primary" @click="action(row, 'start')"
                ><Play :size="14" class="mr-1" />开始</el-button
              >
              <el-button
                v-if="['RUNNING', 'ACTIVE'].includes(row.status)"
                type="primary"
                @click="action(row, 'finish')"
                >结束对比</el-button
              >
              <el-button
                v-if="row.type === 'PUBLISH_TIME' && ['RUNNING', 'ACTIVE'].includes(row.status)"
                :loading="syncing"
                @click="syncSchedules(row)"
                >从排期同步</el-button
              >
              <el-button @click="open(row)">详情</el-button>
            </div>
            <el-button v-else @click="open(row)">详情</el-button>
          </div>
        </article>
        <EmptyState
          v-if="!otherExperiments.length && !featuredExperiment"
          class="xl:col-span-2"
          title="还没有对比"
          ><template #icon><Beaker :size="27" /></template
          ><el-button v-if="canOperate" type="primary" @click="dialog = true"
            >新建对比</el-button
          ></EmptyState
        >
      </div>
    </section>
    <el-dialog v-model="dialog" title="新建对比" width="600px"
      ><el-form label-position="top"
        ><el-form-item label="名称" required><el-input v-model="form.name" /></el-form-item
        ><el-form-item label="对比什么"
          ><el-radio-group v-model="form.type"
            ><el-radio-button value="CONTENT_EFFICIENCY">内容效果</el-radio-button
            ><el-radio-button value="PUBLISH_TIME">发布时间</el-radio-button></el-radio-group
          ></el-form-item
        ><el-form-item label="想验证什么" required
          ><el-input
            v-model="form.hypothesis"
            type="textarea"
            :rows="3"
            placeholder="例如：按系统推荐时间发，互动会不会比平时固定时间更好"
        /></el-form-item>
        <div class="grid grid-cols-2 gap-4">
          <el-form-item label="平时怎么发（对照）"
            ><el-input
              v-model="form.control_description"
              type="textarea"
              :rows="3"
              placeholder="例如：团队平时固定晚上 8 点发" /></el-form-item
          ><el-form-item label="按系统推荐发"
            ><el-input
              v-model="form.treatment_description"
              type="textarea"
              :rows="3"
              placeholder="例如：按活跃度分析给出的推荐时间发"
          /></el-form-item></div></el-form
      ><template #footer
        ><el-button @click="dialog = false">取消</el-button
        ><el-button type="primary" @click="create">创建</el-button></template
      ></el-dialog
    ><el-drawer v-model="drawer" title="对比详情" size="520px"
      ><template v-if="detail"
        ><div class="space-y-5">
          <div>
            <el-tag :type="statusType(detail.status)" round>{{
              statusLabel(detail.status)
            }}</el-tag>
            <h3 class="mt-3 text-xl font-semibold">{{ detail.name }}</h3>
            <p class="section-label mt-5">想验证的事</p>
            <p class="mt-2 text-sm leading-6 text-muted">{{ detail.hypothesis }}</p>
            <div
              v-if="detail.hasSimulatedData"
              class="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800"
            >
              当前是本地演示数据，只用来走流程，不能当真实运营结论。
            </div>
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div class="comparison-cell">
              <small>按平时时间发</small>
              <p>{{ detail.controlDescription }}</p>
            </div>
            <div class="comparison-cell accent">
              <small>按推荐时间发</small>
              <p>{{ detail.treatmentDescription }}</p>
            </div>
          </div>
          <div>
            <p class="section-label">两边互动率</p>
            <div class="mt-3 grid grid-cols-2 gap-3">
              <div class="rounded-xl border border-line p-4">
                <small class="text-muted">按平时时间发</small>
                <strong class="mt-2 block text-2xl">{{
                  formatPercent(controlStats.engagementRate)
                }}</strong>
                <span class="mt-1 block text-xs text-muted"
                  >{{ controlStats.sampleCount || 0 }} 条</span
                >
              </div>
              <div class="rounded-xl border border-blue-200 bg-blue-50 p-4">
                <small class="text-blue-700">按推荐时间发</small>
                <strong class="mt-2 block text-2xl text-blue-700">{{
                  formatPercent(treatmentStats.engagementRate)
                }}</strong>
                <span class="mt-1 block text-xs text-blue-600"
                  >{{ treatmentStats.sampleCount || 0 }} 条</span
                >
              </div>
            </div>
            <div class="mt-3 rounded-xl bg-surface p-4 text-sm leading-6 text-ink">
              {{ conclusionText() }}
            </div>
          </div>
          <div>
            <p class="section-label">样本明细（{{ detail.samples?.length || 0 }}）</p>
            <div class="mt-3 max-h-80 divide-y divide-line overflow-auto">
              <div v-for="(sample, index) in detail.samples" :key="sample.id" class="py-3">
                <div class="flex justify-between">
                  <span class="text-sm font-medium"
                    >{{ groupLabel(sample.groupType) }}样本 {{ index + 1 }}</span
                  >
                  <div class="flex items-center gap-2">
                    <span class="meta-chip">{{ assignmentLabel(sample.assignmentSource) }}</span>
                    <span class="meta-chip">{{ groupLabel(sample.groupType) }}</span>
                  </div>
                </div>
                <p v-if="sample.sampleLabel" class="mt-1 text-xs text-muted">
                  {{ sample.sampleLabel }}
                </p>
                <p v-if="sample.assignmentReason" class="mt-1 text-xs text-muted">
                  分组依据：{{ sample.assignmentReason }}
                </p>
                <div class="mt-2 flex items-center justify-between text-xs text-muted">
                  <span>互动率 {{ formatPercent(sample.metricValueJson?.engagementRate) }}</span>
                  <span>{{ formatDate(sample.createdAt) }}</span>
                </div>
                <el-button
                  v-if="canOperate && detail.type === 'PUBLISH_TIME'"
                  link
                  type="primary"
                  class="mt-1"
                  @click="openOverride(sample as ExperimentSampleRow)"
                  >调整分组</el-button
                >
              </div>
            </div>
          </div>
          <div>
            <p class="section-label">结论</p>
            <p class="mt-2 rounded-xl border border-line p-4 text-sm leading-6 text-muted">
              {{ detail.conclusion || conclusionText() }}
            </p>
          </div>
        </div></template
      ></el-drawer
    >
    <el-dialog v-model="overrideDialog" title="调整这篇归哪一边" width="480px">
      <el-form label-position="top">
        <el-form-item label="归到哪边" required>
          <el-radio-group v-model="overrideForm.group_type">
            <el-radio-button value="TREATMENT">按推荐时间发</el-radio-button>
            <el-radio-button value="CONTROL">按平时时间发</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="调整原因" required>
          <el-input v-model="overrideForm.reason" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="overrideDialog = false">取消</el-button>
        <el-button type="primary" @click="submitOverride">保存调整</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.hero-panel {
  margin-top: 16px;
  padding: 20px 22px;
}
.hero-panel__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.hero-panel__stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 18px;
}
.hero-panel__stats article {
  border: 1px solid var(--sf-line, #e5e7eb);
  border-radius: 10px;
  background: #f8f9fb;
  padding: 14px 16px;
}
.hero-panel__stats article.is-highlight {
  border-color: #bfdbfe;
  background: #eff6ff;
}
.hero-panel__stats span {
  display: block;
  color: #667085;
  font-size: 12px;
}
.hero-panel__stats strong {
  display: block;
  margin-top: 6px;
  color: #172033;
  font-size: 24px;
  font-weight: 700;
  line-height: 1.1;
}
.hero-panel__stats small {
  display: block;
  margin-top: 4px;
  color: #98a2b3;
  font-size: 11px;
}
.hero-panel__note {
  margin: 14px 0 16px;
  color: #475467;
  font-size: 13px;
  line-height: 1.6;
}
.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.experiment-result {
  color: #172033;
  font-size: 14px;
  line-height: 1.6;
}
.source-pill {
  border-radius: 999px;
  background: #f1f5f9;
  color: #475467;
  font-size: 11px;
  padding: 2px 8px;
}
.experiment-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 18px;
  border-top: 1px solid #e5e7eb;
  padding-top: 14px;
}
.experiment-footer > span {
  color: #667085;
  font-size: 12px;
  white-space: nowrap;
}
.experiment-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}
</style>
