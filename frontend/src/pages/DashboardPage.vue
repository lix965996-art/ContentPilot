<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  AlertCircle,
  ArrowUpRight,
  CalendarDays,
  FilePlus2,
  PenLine,
  Upload,
} from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import { getApiErrorMessage } from '@/api/client'
import { workflowApi } from '@/api/workflow'
import ChartPanel from '@/components/ChartPanel.vue'
import AnimatedNumber from '@/components/AnimatedNumber.vue'
import EmptyState from '@/components/EmptyState.vue'
import PlatformIcon from '@/components/PlatformIcon.vue'
import Skeleton from '@/components/Skeleton.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { useAuthStore } from '@/stores/auth'
import type { Article, Schedule } from '@/types/business'
import { platformNames } from '@/types/business'

const router = useRouter()
const auth = useAuthStore()
const loading = ref(true)
const dashboard = ref<Record<string, any>>({})
const overview = ref<Record<string, number>>({})
const recentArticles = ref<Article[]>([])
const schedules = ref<Schedule[]>([])
const ranking = ref<Array<Record<string, any>>>([])
const canOperate = computed(() => auth.hasRole(['ADMIN', 'OPERATOR']))
const todaySchedules = computed(() => {
  const today = new Date().toDateString()
  return schedules.value.filter((item) => new Date(item.scheduledAt).toDateString() === today)
})
const tasks = computed(() => [
  { label: '版本待审核', value: dashboard.value.stats?.pendingReview || 0, route: 'articles' },
  { label: '内容待排期', value: dashboard.value.stats?.pendingSchedule || 0, route: 'calendar' },
  {
    label: '发布失败',
    value: dashboard.value.stats?.failed || 0,
    route: canOperate.value ? 'publish' : 'calendar',
    danger: true,
  },
])
const trendOption = computed(() => ({
  animationDuration: 500,
  grid: { left: 4, right: 4, top: 8, bottom: 4 },
  tooltip: { trigger: 'axis', confine: true },
  xAxis: {
    type: 'category',
    show: false,
    data: (dashboard.value.trend || []).map((x: any) => x.date),
  },
  yAxis: { type: 'value', show: false },
  series: [
    {
      type: 'line',
      smooth: 0.35,
      showSymbol: false,
      data: (dashboard.value.trend || []).map((x: any) => x.engagement),
      lineStyle: { color: '#007aff', width: 2 },
      areaStyle: { color: 'rgba(0,122,255,.06)' },
    },
  ],
}))

async function load() {
  loading.value = true
  try {
    const [dashboardData, articlesData, scheduleData, overviewData, rankingData] =
      await Promise.all([
        workflowApi.dashboard(),
        workflowApi.articles({ page_size: 5 }),
        workflowApi.schedules(),
        workflowApi.analyticsOverview(),
        workflowApi.analyticsRanking(),
      ])
    dashboard.value = dashboardData
    recentArticles.value = articlesData.items
    schedules.value = scheduleData
    overview.value = overviewData
    ranking.value = rankingData
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="dashboard-page">
    <Skeleton v-if="loading" :lines="6" />
    <template v-else>
      <section class="task-strip" aria-label="待处理事项">
        <span class="task-strip-title">待处理</span>
        <button
          v-for="task in tasks"
          :key="task.label"
          :class="{ danger: task.danger && task.value }"
          @click="router.push({ name: task.route })"
        >
          <b><AnimatedNumber :value="task.value" /></b> 个{{ task.label
          }}<ArrowUpRight :size="14" />
        </button>
      </section>

      <div class="dashboard-columns">
        <section class="workspace-section recent-content">
          <header>
            <h2>最近内容</h2>
            <button @click="router.push({ name: 'articles' })">查看全部</button>
          </header>
          <div v-if="recentArticles.length" class="recent-list">
            <article v-for="item in recentArticles" :key="item.id">
              <div class="recent-cover">
                <span>{{ item.title.slice(0, 1) }}</span>
              </div>
              <button
                class="recent-copy"
                @click="router.push({ name: 'articles', query: { edit: item.id } })"
              >
                <b>{{ item.title }}</b
                ><small>{{ item.summary || item.sourceText }}</small>
              </button>
              <div class="recent-platforms">
                <PlatformIcon
                  v-for="variant in item.variants || []"
                  :key="variant.id"
                  :platform="variant.platform"
                  size="sm"
                />
              </div>
              <StatusBadge :status="item.status" />
              <time>{{
                new Date(item.updatedAt).toLocaleDateString('zh-CN', {
                  month: 'numeric',
                  day: 'numeric',
                })
              }}</time>
              <button
                v-if="canOperate"
                class="continue-button"
                @click="router.push({ name: 'studio', query: { article: item.id } })"
              >
                <PenLine :size="14" />继续编辑
              </button>
            </article>
          </div>
          <EmptyState v-else title="还没有内容">
            <template #icon><FilePlus2 :size="22" /></template>
            <el-button
              v-if="canOperate"
              size="small"
              type="primary"
              @click="router.push({ name: 'articles', query: { create: '1' } })"
              >新建内容</el-button
            >
          </EmptyState>
        </section>

        <section class="workspace-section today-schedule">
          <header>
            <h2>今日排期</h2>
            <button @click="router.push({ name: 'calendar' })">日历</button>
          </header>
          <div v-if="todaySchedules.length" class="compact-timeline">
            <button
              v-for="item in todaySchedules.slice(0, 5)"
              :key="item.id"
              @click="router.push({ name: canOperate ? 'publish' : 'calendar' })"
            >
              <time>{{
                new Date(item.scheduledAt).toLocaleTimeString('zh-CN', {
                  hour: '2-digit',
                  minute: '2-digit',
                })
              }}</time>
              <PlatformIcon :platform="item.platform" size="sm" />
              <span
                ><b>{{ platformNames[item.platform] }}</b
                ><small>{{ item.articleTitle }}</small></span
              >
              <StatusBadge :status="item.status" />
            </button>
          </div>
          <EmptyState v-else title="今天没有排期">
            <template #icon><CalendarDays :size="22" /></template>
            <el-button v-if="canOperate" size="small" @click="router.push({ name: 'calendar' })"
              >安排内容</el-button
            >
          </EmptyState>
        </section>
      </div>

      <section class="workspace-section performance-strip">
        <header>
          <h2>最近表现</h2>
          <button @click="router.push({ name: 'analytics' })">查看数据</button>
        </header>
        <div v-if="dashboard.trend?.length" class="performance-content">
          <div class="performance-metric">
            <span>平均互动率</span><strong>{{ overview.engagementRate || 0 }}%</strong
            ><small>基于 {{ overview.sampleCount || 0 }} 条数据</small>
          </div>
          <ChartPanel :option="trendOption" height="112px" />
          <div class="best-content">
            <span>最佳内容</span><b>{{ ranking[0]?.title || '—' }}</b
            ><small>{{ ranking[0]?.engagementRate || 0 }}% 互动率</small>
          </div>
        </div>
        <EmptyState v-else title="还没有互动数据" description="导入发布数据后生成趋势">
          <template #icon><AlertCircle :size="22" /></template>
          <el-button v-if="canOperate" size="small" @click="router.push({ name: 'analytics' })"
            ><Upload :size="14" class="mr-1" />导入数据</el-button
          >
        </EmptyState>
      </section>
    </template>
  </div>
</template>
