<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Download, FileSpreadsheet, Plus, ScrollText, Upload } from 'lucide-vue-next'
import PageHeader from '@/components/PageHeader.vue'
import ChartPanel from '@/components/ChartPanel.vue'
import { workflowApi } from '@/api/workflow'
import { apiClient, getApiErrorMessage } from '@/api/client'
const overview = ref<Record<string, number>>({})
const platforms = ref<Array<any>>([])
const times = ref<Array<any>>([])
const ranking = ref<Array<any>>([])
const summary = ref<Record<string, any>>()
const importing = ref(false)
const manualOpen = ref(false)
const schedules = ref<Array<any>>([])
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
const platformOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 48, right: 16, top: 20, bottom: 32 },
  xAxis: { type: 'category', data: platforms.value.map((x) => x.name) },
  yAxis: { type: 'value' },
  series: [
    {
      type: 'bar',
      data: platforms.value.map((x) => x.engagementRate),
      barWidth: 34,
      itemStyle: { color: '#2563eb', borderRadius: [5, 5, 0, 0] },
    },
  ],
}))
const timeOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 48, right: 16, top: 20, bottom: 32 },
  xAxis: {
    type: 'category',
    data: times.value.map((x) => (x.name === 'RECOMMENDED_TIME' ? '推荐时间组' : '固定时间组')),
  },
  yAxis: { type: 'value' },
  series: [
    {
      type: 'bar',
      data: times.value.map((x) => x.engagementRate),
      barWidth: 42,
      itemStyle: {
        color: (p: any) => (p.dataIndex === 0 ? '#7c3aed' : '#94a3b8'),
        borderRadius: [5, 5, 0, 0],
      },
    },
  ],
}))
async function load() {
  ;[overview.value, platforms.value, times.value, ranking.value] = await Promise.all([
    workflowApi.analyticsOverview(),
    workflowApi.analyticsPlatforms(),
    workflowApi.analyticsTimes(),
    workflowApi.analyticsRanking(),
  ])
}
async function upload(options: any) {
  importing.value = true
  const body = new FormData()
  body.append('file', options.file)
  try {
    const response = await apiClient.post('/analytics/import', body, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    ElMessage.success(`导入完成：成功 ${response.data.data.successCount} 行`)
    await load()
  } catch (e) {
    ElMessage.error(getApiErrorMessage(e))
  } finally {
    importing.value = false
  }
}
async function aiSummary() {
  summary.value = await workflowApi.analyticsSummary()
}
async function download(path: string) {
  try {
    const response = await apiClient.get(path, { responseType: 'blob' })
    const url = URL.createObjectURL(response.data)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = path.endsWith('template')
      ? 'socialflow-analytics-template.xlsx'
      : 'socialflow-report.html'
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
onMounted(() => load().catch((e) => ElMessage.error(getApiErrorMessage(e))))
</script>
<template>
  <div>
    <PageHeader
      title="数据复盘"
      description="导入经过核验的互动数据，对比平台、内容和发布时间实验。"
      ><el-button @click="openManual"><Plus :size="15" class="mr-2" />手工录入</el-button
      ><el-button @click="download('/analytics/template')"
        ><Download :size="15" class="mr-2" />下载模板</el-button
      ><el-upload :show-file-list="false" :http-request="upload" accept=".csv,.xlsx"
        ><el-button type="primary" :loading="importing"
          ><Upload :size="15" class="mr-2" />导入数据</el-button
        ></el-upload
      ></PageHeader
    >
    <div class="notice-strip">
      <FileSpreadsheet :size="16" /><span
        >当前统计 {{ overview.sampleCount || 0 }} 条记录；导入数据前请确认平台口径和日期。</span
      >
    </div>
    <section class="metric-grid">
      <article>
        <span>样本数</span><strong>{{ overview.sampleCount || 0 }}</strong
        ><small>条互动记录</small>
      </article>
      <article>
        <span>总曝光</span><strong>{{ (overview.impressions || 0).toLocaleString() }}</strong
        ><small>impressions</small>
      </article>
      <article>
        <span>总互动</span><strong>{{ (overview.engagementTotal || 0).toLocaleString() }}</strong
        ><small>点赞、评论、收藏、转发</small>
      </article>
      <article>
        <span>互动率</span><strong>{{ overview.engagementRate || 0 }}%</strong
        ><small>互动总量 / 曝光</small>
      </article>
    </section>
    <section class="mt-4 grid gap-4 lg:grid-cols-2">
      <article class="panel rounded-xl p-5">
        <p class="section-label">平台对比</p>
        <h2 class="section-title mt-1">平均互动率</h2>
        <ChartPanel :option="platformOption" />
      </article>
      <article class="panel rounded-xl p-5">
        <p class="section-label">时间实验</p>
        <h2 class="section-title mt-1">推荐时间 vs 固定时间</h2>
        <ChartPanel :option="timeOption" />
      </article>
    </section>
    <section class="mt-4 grid gap-4 lg:grid-cols-[1.3fr_1fr]">
      <article class="panel rounded-xl p-5">
        <div class="flex justify-between">
          <div>
            <p class="section-label">Content ranking</p>
            <h2 class="section-title mt-1">表现最佳内容</h2>
          </div>
          <el-button link @click="download('/analytics/report')">导出 HTML 报告</el-button>
        </div>
        <div class="mt-4 divide-y divide-line">
          <div
            v-for="(item, index) in ranking"
            :key="item.scheduleId"
            class="flex items-center gap-3 py-3"
          >
            <span class="rank-number">{{ index + 1 }}</span>
            <div class="min-w-0 flex-1">
              <p class="truncate text-sm font-medium">{{ item.title }}</p>
              <p class="mt-1 text-xs text-muted">{{ item.platform }} · {{ item.dataSource }}</p>
            </div>
            <strong class="text-sm text-brand">{{ item.engagementRate }}%</strong>
          </div>
        </div>
      </article>
      <article class="panel rounded-xl p-5">
        <div class="flex items-start justify-between">
          <div>
            <p class="section-label">AI review</p>
            <h2 class="section-title mt-1">复盘摘要</h2>
          </div>
          <el-button type="primary" plain @click="aiSummary"
            ><ScrollText :size="15" class="mr-1" />生成摘要</el-button
          >
        </div>
        <template v-if="summary"
          ><p class="mt-5 text-sm leading-7">{{ summary.summary }}</p>
          <ul class="mt-4 space-y-2 text-sm text-muted">
            <li v-for="item in summary.keyFindings" :key="item">• {{ item }}</li>
            <li v-for="item in summary.recommendations" :key="item">→ {{ item }}</li>
          </ul>
          <div class="notice-strip mt-4 !bg-amber-50 !text-amber-800">
            {{ summary.limitations?.[0] }}
          </div></template
        >
        <div v-else class="empty-state min-h-64">
          <ScrollText :size="27" />
          <p>生成数据摘要</p>
          <span>只根据数据库中的当前样本得出结论。</span>
        </div>
      </article>
    </section>
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
          <el-form-item label="统计日期"
            ><el-date-picker v-model="metric.metric_date" value-format="YYYY-MM-DD" class="!w-full"
          /></el-form-item>
          <el-form-item label="实验分组"
            ><el-select v-model="metric.group_type" class="w-full"
              ><el-option label="推荐时间组" value="RECOMMENDED_TIME" /><el-option
                label="固定时间组"
                value="FIXED_TIME" /></el-select
          ></el-form-item>
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
      <template #footer
        ><el-button @click="manualOpen = false">取消</el-button
        ><el-button type="primary" @click="saveManual">保存数据</el-button></template
      >
    </el-dialog>
  </div>
</template>
