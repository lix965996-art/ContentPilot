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
import type { ActivityAnalysis, RecommendationEffect } from '@/types/business'

const router = useRouter()
const auth = useAuthStore()
const canOperate = computed(() => auth.canManageBusiness)
const activeTab = ref<'history' | 'publish' | 'chain'>('history')

const overview = ref<Record<string, number>>({})
const ranking = ref<Array<Record<string, any>>>([])
const importing = ref(false)
const manualOpen = ref(false)
const schedules = ref<Array<Record<string, any>>>([])
const historyTotal = ref(0)
const historyAnalysis = ref<ActivityAnalysis>()
const historyLoading = ref(false)
const effect = ref<RecommendationEffect>()

const publishSampleCount = computed(() => overview.value.sampleCount || 0)
const hasPublishData = computed(() => publishSampleCount.value > 0)
const hasHistoryData = computed(() => historyTotal.value > 0)

const metric = ref<Record<string, any>>({
  schedule_id: 0,
  platform: 'WEIBO',
  metric_date: new Date().toISOString().slice(0, 10),
  impressions: 0,
  likes: 0,
  comments: 0,
  collects: 0,
  shares: 0,
  followers: 0,
  group_type: 'RECOMMENDED_TIME',
  data_source: 'MANUAL',
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
  const [overviewData, rankingData, scheduleData, effectData, historyData] = await Promise.all([
    workflowApi.analyticsOverview(),
    workflowApi.analyticsRanking(),
    workflowApi.schedules(),
    workflowApi.recommendationEffect(),
    workflowApi.historyBatches(),
  ])
  overview.value = overviewData
  ranking.value = rankingData
  schedules.value = scheduleData
  effect.value = effectData
  historyTotal.value = historyData.totalRecords || 0

  if (historyTotal.value) {
    await loadHistoryAnalysis()
  }

  if (!hasHistoryData.value && hasPublishData.value) {
    activeTab.value = 'publish'
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
    const response = await apiClient.get(path, { responseType: 'blob' })
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
      <PublishReviewPanel
        v-if="hasPublishData"
        :overview="overview"
        :ranking="ranking"
        :effect="effect"
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
      <DecisionChainPanel v-if="hasPublishData" :effect="effect" />
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
