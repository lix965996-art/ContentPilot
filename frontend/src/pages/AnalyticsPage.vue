<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { UploadRequestOptions } from 'element-plus'
import { Download, FileSpreadsheet, Plus, Upload } from 'lucide-vue-next'
import PageHeader from '@/components/PageHeader.vue'
import HistorySlotInsightPanel from '@/components/HistorySlotInsightPanel.vue'
import PublishReviewPanel from '@/components/PublishReviewPanel.vue'
import DecisionChainPanel from '@/components/DecisionChainPanel.vue'
import EmptyState from '@/components/EmptyState.vue'
import Skeleton from '@/components/Skeleton.vue'
import { workflowApi } from '@/api/workflow'
import { apiClient, getApiErrorMessage } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import type { ActivityAnalysis, DataScope, RecommendationEffect } from '@/types/business'

const router = useRouter()
const auth = useAuthStore()
const canOperate = computed(() => auth.canManageBusiness)
const activeTab = ref<'history' | 'publish' | 'chain'>('history')

const overview = ref<Record<string, any>>({})
const dataScope = ref<DataScope>('REAL')
const ranking = ref<Array<Record<string, any>>>([])
const importing = ref(false)
const manualOpen = ref(false)
const schedules = ref<Array<Record<string, any>>>([])
const historyTotal = ref(0)
const historyAnalysis = ref<ActivityAnalysis>()
const historyLoading = ref(false)
const effect = ref<RecommendationEffect>()
const publishLoading = ref(false)
let loadRevision = 0

const publishSampleCount = computed(() => overview.value.sampleCount || 0)
const hasPublishData = computed(() => publishSampleCount.value > 0)
const hasHistoryData = computed(() => historyTotal.value > 0)

function localDateString(date = new Date()) {
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

const metric = ref<Record<string, any>>({
  schedule_id: 0,
  platform: 'WEIBO',
  metric_date: localDateString(),
  impressions: 0,
  likes: 0,
  comments: 0,
  collects: 0,
  shares: 0,
  followers: 0,
  group_type: 'RECOMMENDED_TIME',
  data_source: 'MANUAL',
  metric_basis: 'IMPRESSIONS',
})

async function loadHistoryAnalysis() {
  historyLoading.value = true
  historyAnalysis.value = undefined
  try {
    historyAnalysis.value = await workflowApi.activityAnalysis({
      source_scope: 'ALL',
      window: 'ALL',
    })
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    historyLoading.value = false
  }
}

async function load() {
  const revision = ++loadRevision
  const scope = dataScope.value
  publishLoading.value = true
  overview.value = {}
  ranking.value = []
  effect.value = undefined
  try {
    const [overviewData, rankingData, scheduleData, effectData, historyData] = await Promise.all([
      workflowApi.analyticsOverview({ data_scope: scope }),
      workflowApi.analyticsRanking({ data_scope: scope }),
      workflowApi.schedules(),
      workflowApi.recommendationEffect({ data_scope: scope }),
      workflowApi.historyBatches(),
    ])
    if (revision !== loadRevision || scope !== dataScope.value) return
    overview.value = overviewData
    ranking.value = rankingData
    schedules.value = scheduleData
    effect.value = effectData
    historyTotal.value = historyData.totalRecords || 0

    if (historyTotal.value) {
      await loadHistoryAnalysis()
    }

    if (revision !== loadRevision || scope !== dataScope.value) return
    if (!hasHistoryData.value && hasPublishData.value) {
      activeTab.value = 'publish'
    }
  } catch (error) {
    if (revision === loadRevision && scope === dataScope.value)
      ElMessage.error(getApiErrorMessage(error))
  } finally {
    if (revision === loadRevision) publishLoading.value = false
  }
}

async function upload(options: UploadRequestOptions) {
  importing.value = true
  const body = new FormData()
  body.append('file', options.file)
  try {
    const response = await apiClient.post('/analytics/import', body, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    ElMessage.success(`导入完成：成功 ${response.data.data.successCount} 行`)
    await load()
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    importing.value = false
  }
}

async function download(path: string) {
  try {
    const response = await apiClient.get(path, {
      responseType: 'blob',
      params: { data_scope: dataScope.value },
    })
    const url = URL.createObjectURL(response.data)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = path.endsWith('template')
      ? 'contentpilot-analytics-template.xlsx'
      : 'contentpilot-report.html'
    anchor.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '下载失败'))
  }
}

async function openManual() {
  schedules.value = await workflowApi.schedules()
  const first = schedules.value[0]
  if (!first) return ElMessage.warning('请先创建排期任务')
  metric.value.schedule_id = first.id
  metric.value.platform = first.platform
  manualOpen.value = true
}

function syncPlatform() {
  const row = schedules.value.find((item) => item.id === metric.value.schedule_id)
  if (row) metric.value.platform = row.platform
}

async function saveManual() {
  try {
    await apiClient.post('/analytics/manual', metric.value)
    manualOpen.value = false
    ElMessage.success('互动数据已保存')
    await load()
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  }
}

onMounted(() => load().catch((error) => ElMessage.error(getApiErrorMessage(error))))
</script>

<template>
  <div class="analytics-page">
    <PageHeader title="数据">
      <el-button v-if="canOperate" @click="openManual">
        <Plus :size="15" class="mr-2" />手工录入
      </el-button>
      <el-button @click="download('/analytics/template')">
        <Download :size="15" class="mr-2" />下载模板
      </el-button>
      <el-upload
        v-if="canOperate"
        :show-file-list="false"
        :http-request="upload"
        accept=".csv,.xlsx"
      >
        <el-button type="primary" :loading="importing">
          <Upload :size="15" class="mr-2" />导入复盘数据
        </el-button>
      </el-upload>
    </PageHeader>
    <div class="mt-4 flex flex-wrap items-center gap-3">
      <span class="text-sm text-muted">发布数据范围</span>
      <el-select v-model="dataScope" class="!w-44" aria-label="发布数据范围" @change="load">
        <el-option label="真实数据" value="REAL" />
        <el-option label="演示数据" value="SIMULATED" />
        <el-option label="全部（按来源区分）" value="ALL" />
      </el-select>
      <span v-if="dataScope !== 'REAL'" class="text-xs text-muted"
        >含演示数据，不代表线上发布效果。</span
      >
      <span v-else-if="overview.excludedSimulatedCount" class="text-xs text-muted"
        >已排除 {{ overview.excludedSimulatedCount }} 条演示指标。</span
      >
    </div>

    <div class="analytics-segment">
      <button
        type="button"
        :class="{ active: activeTab === 'history' }"
        @click="activeTab = 'history'"
      >
        历史基线
      </button>
      <button
        type="button"
        :class="{ active: activeTab === 'publish' }"
        @click="activeTab = 'publish'"
      >
        发布复盘
      </button>
      <button type="button" :class="{ active: activeTab === 'chain' }" @click="activeTab = 'chain'">
        决策链路
      </button>
    </div>

    <div v-show="activeTab === 'history'" class="analytics-pane">
      <template v-if="hasHistoryData">
        <Skeleton v-if="historyLoading" :lines="6" />
        <HistorySlotInsightPanel
          v-else-if="historyAnalysis?.sampleCount"
          :analysis="historyAnalysis"
          :loading="historyLoading"
          :can-schedule="canOperate"
          @recalculate="loadHistoryAnalysis"
        />
        <EmptyState
          v-else-if="!historyLoading"
          title="分析结果为空"
          description="历史库有记录，但暂无可用时段。"
        />
      </template>
      <EmptyState v-else title="还没有历史基线数据" description="请先导入历史数据">
        <template #icon><FileSpreadsheet :size="23" /></template>
        <el-button size="small" @click="router.push({ name: 'recommendation' })">
          去导入
        </el-button>
      </EmptyState>
    </div>

    <div v-show="activeTab === 'publish'" class="analytics-pane">
      <Skeleton v-if="publishLoading" :lines="6" />
      <PublishReviewPanel
        v-else-if="hasPublishData"
        :overview="overview"
        :ranking="ranking"
        :effect="effect"
        :data-scope="dataScope"
      />
      <EmptyState v-else title="还没有发布复盘数据" description="导入或手工录入互动指标后查看">
        <template #icon><FileSpreadsheet :size="23" /></template>
        <el-upload
          v-if="canOperate"
          :show-file-list="false"
          :http-request="upload"
          accept=".csv,.xlsx"
        >
          <el-button size="small" type="primary" :loading="importing">导入复盘数据</el-button>
        </el-upload>
      </EmptyState>
    </div>

    <div v-if="activeTab === 'chain'" class="analytics-pane">
      <Skeleton v-if="publishLoading" :lines="6" />
      <DecisionChainPanel v-else-if="hasPublishData" :effect="effect" />
      <EmptyState
        v-else
        title="还没有可追溯的发布记录"
        description="需要至少一条已发布并回收互动数据的内容"
      >
        <template #icon><FileSpreadsheet :size="23" /></template>
      </EmptyState>
    </div>

    <el-dialog v-model="manualOpen" title="手工录入互动数据" width="620px">
      <el-form label-position="top">
        <div class="grid grid-cols-2 gap-x-4">
          <el-form-item label="排期任务" class="col-span-2">
            <el-select
              v-model="metric.schedule_id"
              filterable
              class="w-full"
              @change="syncPlatform"
            >
              <el-option
                v-for="item in schedules"
                :key="item.id"
                :label="`#${item.id} · ${item.articleTitle}`"
                :value="item.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="统计日期">
            <el-date-picker
              v-model="metric.metric_date"
              value-format="YYYY-MM-DD"
              class="!w-full"
            />
          </el-form-item>
          <el-form-item label="归到哪边">
            <el-select v-model="metric.group_type" class="w-full">
              <el-option label="按推荐时间发" value="RECOMMENDED_TIME" />
              <el-option label="按平时时间发" value="FIXED_TIME" />
            </el-select>
          </el-form-item>
          <el-form-item label="互动率分母" required>
            <el-select v-model="metric.metric_basis" class="w-full">
              <el-option label="曝光量" value="IMPRESSIONS" />
              <el-option label="粉丝数" value="FOLLOWERS" />
              <el-option label="尚未确认" value="UNKNOWN" />
            </el-select>
          </el-form-item>
          <el-form-item label="数据来源" required>
            <el-select v-model="metric.data_source" class="w-full">
              <el-option label="真实数据（手工录入）" value="MANUAL" />
              <el-option label="演示数据" value="SIMULATED" />
            </el-select>
          </el-form-item>
          <el-form-item
            v-for="field in ['impressions', 'likes', 'comments', 'collects', 'shares', 'followers']"
            :key="field"
            :label="
              {
                impressions: '曝光',
                likes: '点赞',
                comments: '评论',
                collects: '收藏',
                shares: '转发',
                followers: '粉丝',
              }[field]
            "
          >
            <el-input-number v-model="metric[field]" :min="0" class="!w-full" />
          </el-form-item>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="manualOpen = false">取消</el-button>
        <el-button type="primary" @click="saveManual">保存数据</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.analytics-segment {
  display: inline-flex;
  gap: 2px;
  margin-top: 16px;
  padding: 3px;
  border-radius: 12px;
  background: #eef1f5;
}

.analytics-segment button {
  border: none;
  border-radius: 10px;
  background: transparent;
  color: #6b7280;
  font-size: 13px;
  font-weight: 500;
  padding: 8px 18px;
  cursor: pointer;
  transition:
    background 0.15s ease,
    color 0.15s ease,
    box-shadow 0.15s ease;
}

.analytics-segment button.active {
  background: #fff;
  color: #111827;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.06);
}

.analytics-pane {
  margin-top: 14px;
}
</style>
