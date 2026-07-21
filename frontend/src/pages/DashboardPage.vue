<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  AlertTriangle,
  ArrowRight,
  CalendarDays,
  CheckCircle2,
  FileText,
  Plus,
  PenLine,
} from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import { workflowApi } from '@/api/workflow'
import { getApiErrorMessage } from '@/api/client'
import ChartPanel from '@/components/ChartPanel.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { useAuthStore } from '@/stores/auth'
import { platformNames } from '@/types/business'
import type { Platform } from '@/types/business'
const router = useRouter()
const auth = useAuthStore()
const data = ref<Record<string, any>>()
const loading = ref(true)
const dateLabel = new Intl.DateTimeFormat('zh-CN', {
  month: 'long',
  day: 'numeric',
  weekday: 'long',
}).format(new Date())
const trendOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 38, right: 16, top: 20, bottom: 30 },
  xAxis: {
    type: 'category',
    data: (data.value?.trend || []).map((x: any) => x.date.slice(5)),
    axisLine: { lineStyle: { color: '#e6e8ef' } },
  },
  yAxis: { type: 'value', splitLine: { lineStyle: { color: '#eef0f5' } } },
  series: [
    {
      type: 'line',
      smooth: true,
      symbolSize: 6,
      data: (data.value?.trend || []).map((x: any) => x.engagement),
      lineStyle: { color: '#315c4d', width: 2 },
      itemStyle: { color: '#315c4d' },
      areaStyle: { color: 'rgba(49,92,77,.08)' },
    },
  ],
}))
async function load() {
  loading.value = true
  try {
    data.value = await workflowApi.dashboard()
  } catch (e) {
    ElMessage.error(getApiErrorMessage(e))
  } finally {
    loading.value = false
  }
}
function platformLabel(value: string): string {
  return platformNames[value as Platform] || value
}
onMounted(load)
</script>
<template>
  <div v-loading="loading">
    <section class="dashboard-hero">
      <div>
        <p>{{ dateLabel }}</p>
        <h1>早上好，{{ auth.user?.display_name }}</h1>
        <span>今天的原文、审核、排期和数据都在这里。</span>
      </div>
      <div class="flex gap-2">
        <el-button @click="router.push({ name: 'articles' })"
          ><Plus :size="16" class="mr-1" />新建原文</el-button
        ><el-button type="primary" @click="router.push({ name: 'studio' })"
          ><PenLine :size="16" class="mr-1" />生成平台版本</el-button
        >
      </div>
    </section>
    <div class="notice-strip">
      <CheckCircle2 :size="16" /><span>{{ data?.dataNotice }}</span>
    </div>
    <section class="metric-grid">
      <article>
        <span>内容资产</span><strong>{{ data?.stats?.articles || 0 }}</strong
        ><small>篇原文</small><FileText />
      </article>
      <article>
        <span>待审核</span><strong>{{ data?.stats?.pendingReview || 0 }}</strong
        ><small>个平台版本</small><PenLine />
      </article>
      <article>
        <span>待发布</span><strong>{{ data?.stats?.pendingSchedule || 0 }}</strong
        ><small>个排期任务</small><CalendarDays />
      </article>
      <article :class="{ 'is-alert': data?.stats?.failed }">
        <span>发布失败</span><strong>{{ data?.stats?.failed || 0 }}</strong
        ><small>需要处理</small><AlertTriangle />
      </article>
    </section>
    <section class="mt-4 grid gap-4 xl:grid-cols-[1.45fr_.85fr]">
      <article class="panel rounded-xl p-5">
        <div class="panel-heading">
          <div>
            <p class="section-label">近 14 天</p>
            <h2 class="section-title mt-1">最近互动趋势</h2>
          </div>
          <el-button link type="primary" @click="router.push({ name: 'analytics' })"
            >查看完整复盘<ArrowRight :size="14" class="ml-1"
          /></el-button>
        </div>
        <ChartPanel :option="trendOption" height="270px" />
      </article>
      <article class="panel rounded-xl p-5">
        <div class="panel-heading">
          <div>
            <p class="section-label">发布队列</p>
            <h2 class="section-title mt-1">今日排期</h2>
          </div>
          <el-button link @click="router.push({ name: 'calendar' })">日历</el-button>
        </div>
        <div v-if="data?.todaySchedules?.length" class="schedule-list">
          <button
            v-for="item in data.todaySchedules"
            :key="item.id"
            @click="router.push({ name: 'publish' })"
          >
            <span class="schedule-time">{{
              new Date(item.scheduledAt).toLocaleTimeString('zh-CN', {
                hour: '2-digit',
                minute: '2-digit',
              })
            }}</span>
            <div>
              <p>{{ platformLabel(item.platform) }}</p>
              <small>发布任务 #{{ item.id }}</small>
            </div>
            <StatusBadge :status="item.status" />
          </button>
        </div>
        <div v-else class="empty-state min-h-64">
          <CalendarDays :size="28" />
          <p>今天没有排期</p>
          <span>前往日历安排下一条内容。</span>
        </div>
      </article>
    </section>
    <section class="mt-4 panel rounded-xl p-5">
      <div class="panel-heading">
        <div>
          <p class="section-label">对照结果</p>
          <h2 class="section-title mt-1">推荐时间与固定时间</h2>
        </div>
        <span class="meta-chip">按实际录入指标统计</span>
      </div>
      <div class="comparison-bars">
        <div v-for="item in data?.timeComparison || []" :key="item.name">
          <div>
            <span>{{ item.name === 'RECOMMENDED_TIME' ? '推荐时间组' : '固定时间组' }}</span
            ><b>{{ item.rate }}%</b>
          </div>
          <div><i :style="{ width: `${Math.min(item.rate * 8, 100)}%` }" /></div>
          <small>{{ item.samples }} 个样本</small>
        </div>
      </div>
    </section>
  </div>
</template>
