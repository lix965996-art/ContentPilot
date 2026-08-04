<script setup lang="ts">
import { computed, ref } from 'vue'
import ChartPanel from '@/components/ChartPanel.vue'
import { workflowApi } from '@/api/workflow'
import type { PublishDecisionChain, RecommendationEffect } from '@/types/business'
import { analysisPlatformNames, platformNames } from '@/types/business'
import { AXIS_STYLE, CHART_COLORS, tooltipStyle } from '@/config/echartsTheme'
import {
  evaluatePublishReviewRecord,
  formatDateTime,
  formatDeviation,
  groupStats,
  type PublishReviewRecord,
} from '@/utils/publishReviewMetrics'

const props = defineProps<{
  overview: Record<string, number>
  ranking: Array<Record<string, unknown>>
  effect?: RecommendationEffect
}>()

const expandedRows = ref<number[]>([])

function displayPlatform(name: string) {
  return analysisPlatformNames[name] || platformNames[name as keyof typeof platformNames] || name
}

function effectItem(scheduleId: number) {
  return props.effect?.items.find((item) => item.scheduleId === scheduleId)
}

function buildRawRecord(row: Record<string, unknown>) {
  const scheduleId = row.scheduleId as number
  const linked = effectItem(scheduleId)
  const platformKey = String(row.platform || linked?.platform || '')
  return evaluatePublishReviewRecord({
    scheduleId,
    title: String(row.title || linked?.title || '未知内容'),
    platformKey,
    platformLabel: displayPlatform(platformKey),
    dataSource: row.dataSource ? String(row.dataSource) : undefined,
    timeSource: linked?.timeSource || 'CUSTOM',
    scheduledAt: linked?.scheduledAt ?? null,
    recommendedAt: linked?.recommendedAt ?? null,
    actualPublishAt: linked?.actualPublishAt ?? null,
    deviationMinutes: linked?.deviationMinutes ?? null,
    likes: typeof row.likes === 'number' ? row.likes : null,
    comments: typeof row.comments === 'number' ? row.comments : null,
    collects: typeof row.collects === 'number' ? row.collects : null,
    shares: typeof row.shares === 'number' ? row.shares : null,
    followers: typeof row.followers === 'number' ? row.followers : null,
    engagementTotal: Number(row.engagementTotal ?? linked?.engagementTotal ?? 0) || null,
    apiEngagementRate:
      typeof row.engagementRate === 'number'
        ? row.engagementRate
        : (linked?.engagementRate ?? null),
    impressions:
      typeof row.impressions === 'number' ? row.impressions : (linked?.impressions ?? null),
  })
}

const records = computed<PublishReviewRecord[]>(() => {
  const fromRanking = props.ranking.map((row) => buildRawRecord(row))
  if (fromRanking.length) return fromRanking

  return (props.effect?.items || [])
    .filter((item) => item.sampleCount > 0)
    .map((item) =>
      buildRawRecord({
        scheduleId: item.scheduleId,
        title: item.title,
        platform: item.platform,
        engagementTotal: item.engagementTotal,
        engagementRate: item.engagementRate,
      }),
    )
})

const totalCount = computed(() => props.overview.sampleCount || records.value.length)
const realValidCount = computed(() => records.value.filter((row) => row.isRealValid).length)
const simulatedCount = computed(
  () => records.value.filter((row) => !row.participatesInRealEffect).length,
)
const recommendedCount = computed(
  () => records.value.filter((row) => row.isRecommendedGroup).length,
)
const customCount = computed(() => records.value.filter((row) => !row.isRecommendedGroup).length)

/**
 * SIMULATED records never count as measured platform effect, but excluding them
 * leaves the comparison empty on a demo dataset. Opt in explicitly and badge it.
 */
const includeSimulated = ref(true)

const comparableRecords = computed(() =>
  records.value.filter(
    (row) => row.rateStatus === 'ok' && (row.participatesInRealEffect || includeSimulated.value),
  ),
)

const recommendedStats = computed(() =>
  groupStats(comparableRecords.value.filter((row) => row.isRecommendedGroup)),
)
const customStats = computed(() =>
  groupStats(comparableRecords.value.filter((row) => !row.isRecommendedGroup)),
)

const canCompareUplift = computed(
  () => recommendedStats.value.validCount >= 3 && customStats.value.validCount >= 3,
)

const upliftPercent = computed(() => {
  if (!canCompareUplift.value) return null
  const recAvg = recommendedStats.value.avg
  const customAvg = customStats.value.avg
  if (recAvg === null || customAvg === null || customAvg === 0) return null
  return Number((((recAvg - customAvg) / customAvg) * 100).toFixed(2))
})

const plottableRecords = computed(() =>
  records.value.filter((row) => row.rateStatus === 'ok' && row.engagementRate !== null),
)

const scatterOption = computed(() => {
  const plottable = plottableRecords.value
  const labels = plottable.map((row) => row.title.slice(0, 12))
  const maxRate = Math.max(...plottable.map((row) => row.engagementRate || 0), 12)

  return {
    grid: { left: 96, right: 16, top: 8, bottom: 28 },
    tooltip: {
      ...tooltipStyle(),
      trigger: 'item',
      formatter: (param: { dataIndex: number }) => {
        const row = plottable[param.dataIndex]
        if (!row) return ''
        return [
          `<strong>${row.title}</strong>`,
          `${row.platformLabel} · ${row.timeSourceLabel}`,
          `互动率 ${row.rateStatusLabel}`,
          `浏览 ${row.impressions ?? '—'}`,
        ].join('<br/>')
      },
    },
    xAxis: {
      type: 'value',
      name: '互动率 %',
      max: Math.ceil(maxRate * 1.15),
      ...AXIS_STYLE,
    },
    yAxis: {
      type: 'category',
      data: labels,
      axisLabel: { fontSize: 11, color: CHART_COLORS.muted, width: 88, overflow: 'truncate' },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series: [
      {
        type: 'scatter',
        symbolSize: 11,
        data: plottable.map((row, index) => ({
          value: [row.engagementRate, index],
          itemStyle: { color: row.isRecommendedGroup ? CHART_COLORS.brand : '#94a3b8' },
        })),
      },
    ],
  }
})

const groupPieOption = computed(() => {
  const data = [
    { name: '推荐时段', value: recommendedCount.value },
    { name: '自选时段', value: customCount.value },
  ].filter((item) => item.value > 0)

  return {
    color: ['#2563EB', '#CBD5E1'],
    tooltip: {
      ...tooltipStyle(),
      trigger: 'item',
      formatter: (p: { name: string; value: number; percent: number }) =>
        `${p.name}<br/><b>${p.value}</b> 条 · ${p.percent}%`,
    },
    legend: {
      bottom: 0,
      icon: 'circle',
      itemWidth: 8,
      itemHeight: 8,
      textStyle: { color: '#667085', fontSize: 11 },
    },
    series: [
      {
        type: 'pie',
        radius: ['48%', '68%'],
        center: ['50%', '45%'],
        itemStyle: { borderColor: '#fff', borderWidth: 2 },
        label: { show: true, formatter: '{d}%', color: '#475467', fontSize: 11 },
        labelLine: { length: 8, length2: 6, lineStyle: { color: '#d0d5dd' } },
        data,
      },
    ],
  }
})

const compareBarOption = computed(() => {
  const rec = recommendedStats.value.avg
  const custom = customStats.value.avg
  return {
    grid: { left: 48, right: 16, top: 28, bottom: 28 },
    tooltip: {
      ...tooltipStyle(),
      trigger: 'axis',
      formatter: (params: Array<{ name: string; value: number | null }>) => {
        const item = params[0]
        if (!item || item.value === null) return `${item?.name || ''}：—`
        return `${item.name}<br/>平均互动率 <b>${item.value}%</b>`
      },
    },
    xAxis: {
      type: 'category',
      data: ['推荐', '自选'],
      axisLabel: { color: CHART_COLORS.muted, fontSize: 11 },
      axisLine: { lineStyle: { color: CHART_COLORS.line } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      name: '%',
      ...AXIS_STYLE,
    },
    series: [
      {
        type: 'bar',
        barMaxWidth: 42,
        label: {
          show: true,
          position: 'top',
          fontSize: 11,
          color: '#475467',
          formatter: (param: { value: number | null }) =>
            param.value === null || param.value === undefined ? '—' : `${param.value}%`,
        },
        data: [
          {
            value: rec,
            itemStyle: { color: '#2563EB', borderRadius: [6, 6, 0, 0] },
          },
          {
            value: custom,
            itemStyle: { color: '#CBD5E1', borderRadius: [6, 6, 0, 0] },
          },
        ],
      },
    ],
  }
})

const sourcePieOption = computed(() => {
  const counts: Record<string, number> = {}
  for (const row of records.value) {
    counts[row.dataSourceLabel] = (counts[row.dataSourceLabel] || 0) + 1
  }
  const data = Object.entries(counts).map(([name, value]) => ({ name, value }))
  return {
    color: ['#2563EB', '#93C5FD', '#CBD5E1', '#64748B'],
    tooltip: {
      ...tooltipStyle(),
      trigger: 'item',
      formatter: (p: { name: string; value: number; percent: number }) =>
        `${p.name}<br/><b>${p.value}</b> 条 · ${p.percent}%`,
    },
    legend: {
      bottom: 0,
      icon: 'circle',
      itemWidth: 8,
      itemHeight: 8,
      textStyle: { color: '#667085', fontSize: 11 },
    },
    series: [
      {
        type: 'pie',
        radius: ['48%', '68%'],
        center: ['50%', '45%'],
        itemStyle: { borderColor: '#fff', borderWidth: 2 },
        label: { show: true, formatter: '{d}%', color: '#475467', fontSize: 11 },
        labelLine: { length: 8, length2: 6, lineStyle: { color: '#d0d5dd' } },
        data,
      },
    ],
  }
})

const decisions = ref<Record<number, PublishDecisionChain>>({})
const decisionLoading = ref<number[]>([])
const decisionErrors = ref<Record<number, string>>({})

async function loadDecision(scheduleId: number) {
  if (decisions.value[scheduleId] || decisionLoading.value.includes(scheduleId)) return
  decisionLoading.value = [...decisionLoading.value, scheduleId]
  delete decisionErrors.value[scheduleId]
  try {
    decisions.value = {
      ...decisions.value,
      [scheduleId]: await workflowApi.publishDecision(scheduleId),
    }
  } catch {
    decisionErrors.value = { ...decisionErrors.value, [scheduleId]: '推荐依据加载失败' }
  } finally {
    decisionLoading.value = decisionLoading.value.filter((id) => id !== scheduleId)
  }
}

function toggleExpand(scheduleId: number) {
  if (expandedRows.value.includes(scheduleId)) {
    expandedRows.value = expandedRows.value.filter((id) => id !== scheduleId)
  } else {
    expandedRows.value = [...expandedRows.value, scheduleId]
    void loadDecision(scheduleId)
  }
}

function percent(value: number) {
  return `${Math.round(value * 100)}%`
}

function hourlyOption(chain: PublishDecisionChain) {
  const { hourly, hour, bestHour } = chain.analysis
  return {
    grid: { left: 34, right: 10, top: 10, bottom: 22 },
    tooltip: {
      ...tooltipStyle(),
      trigger: 'axis',
      formatter: (params: Array<{ name: string; value: number }>) => {
        const item = params[0]
        if (!item) return ''
        return `${item.name}:00<br/>推荐得分 <b>${item.value}</b>`
      },
    },
    xAxis: {
      type: 'category',
      data: hourly.map((item) => item.hour),
      axisLabel: {
        color: CHART_COLORS.muted,
        fontSize: 10,
        interval: 3,
      },
      axisLine: { lineStyle: { color: CHART_COLORS.line } },
      axisTick: { show: false },
    },
    yAxis: { type: 'value', ...AXIS_STYLE },
    series: [
      {
        type: 'bar',
        barCategoryGap: '30%',
        data: hourly.map((item) => ({
          value: item.score,
          itemStyle: {
            color: item.hour === hour ? '#2563EB' : item.hour === bestHour ? '#93C5FD' : '#E5E9F0',
            borderRadius: [3, 3, 0, 0],
          },
        })),
      },
    ],
  }
}
</script>

<template>
  <section class="review-panel">
    <section class="review-kpis">
      <div>
        <span>记录</span>
        <strong>{{ totalCount }}</strong>
      </div>
      <div>
        <span>真实有效</span>
        <strong>{{ realValidCount }}</strong>
      </div>
      <div>
        <span>演示数据</span>
        <strong>{{ simulatedCount }}</strong>
      </div>
      <div>
        <span>推荐时段</span>
        <strong>{{ recommendedCount }}</strong>
      </div>
      <div>
        <span>自选时段</span>
        <strong>{{ customCount }}</strong>
      </div>
      <div v-if="upliftPercent !== null" class="review-kpi-accent">
        <span>推荐提升</span>
        <strong>{{ upliftPercent >= 0 ? '+' : '' }}{{ upliftPercent }}%</strong>
      </div>
    </section>

    <section class="review-charts">
      <article>
        <div class="review-block-head">
          <h3>时段占比</h3>
        </div>
        <ChartPanel :option="groupPieOption" height="200px" />
      </article>
      <article>
        <div class="review-block-head">
          <h3>平均互动率</h3>
        </div>
        <ChartPanel :option="compareBarOption" height="200px" />
      </article>
      <article>
        <div class="review-block-head">
          <h3>数据来源</h3>
        </div>
        <ChartPanel :option="sourcePieOption" height="200px" />
      </article>
    </section>

    <section v-if="plottableRecords.length" class="review-block">
      <div class="review-block-head">
        <h3>效果分布</h3>
        <div class="review-legend">
          <span><i class="dot rec" />推荐</span>
          <span><i class="dot custom" />自选</span>
        </div>
      </div>
      <ChartPanel :option="scatterOption" height="220px" />
    </section>

    <section class="review-block">
      <div class="review-block-head">
        <h3>推荐 vs 自选</h3>
        <label class="review-toggle">
          <input v-model="includeSimulated" type="checkbox" />
          包含演示数据（{{ simulatedCount }} 条）
        </label>
      </div>
      <p v-if="includeSimulated && simulatedCount" class="review-warning">
        当前对比包含 {{ simulatedCount }} 条 SIMULATED
        模拟互动数据，用于演示流程，不代表真实平台效果。
      </p>
      <table class="review-table">
        <thead>
          <tr>
            <th>分组</th>
            <th>有效样本</th>
            <th>平均互动率</th>
            <th>中位互动率</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>推荐</td>
            <td>{{ recommendedStats.validCount }}</td>
            <td>{{ recommendedStats.avg !== null ? `${recommendedStats.avg}%` : '—' }}</td>
            <td>{{ recommendedStats.median !== null ? `${recommendedStats.median}%` : '—' }}</td>
          </tr>
          <tr>
            <td>自选</td>
            <td>{{ customStats.validCount }}</td>
            <td>{{ customStats.avg !== null ? `${customStats.avg}%` : '—' }}</td>
            <td>{{ customStats.median !== null ? `${customStats.median}%` : '—' }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="review-block">
      <div class="review-block-head">
        <h3>明细</h3>
      </div>
      <table class="review-table">
        <thead>
          <tr>
            <th style="width: 36px" />
            <th>标题</th>
            <th>平台</th>
            <th>分组</th>
            <th>互动率</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="row in records" :key="row.scheduleId">
            <tr>
              <td>
                <button type="button" class="expand-btn" @click="toggleExpand(row.scheduleId)">
                  {{ expandedRows.includes(row.scheduleId) ? '−' : '+' }}
                </button>
              </td>
              <td class="title-cell" :title="row.title">{{ row.title }}</td>
              <td>{{ row.platformLabel }}</td>
              <td>
                <span :class="row.isRecommendedGroup ? 'pill-rec' : 'pill-custom'">
                  {{ row.isRecommendedGroup ? '推荐' : '自选' }}
                </span>
              </td>
              <td>{{ row.rateStatusLabel }}</td>
            </tr>
            <tr v-if="expandedRows.includes(row.scheduleId)" class="expand-row">
              <td colspan="5">
                <div class="expand-grid">
                  <div>
                    <span>计划时间</span>
                    <strong>{{ formatDateTime(row.scheduledAt) }}</strong>
                  </div>
                  <div>
                    <span>推荐时间</span>
                    <strong>{{ formatDateTime(row.recommendedAt) }}</strong>
                  </div>
                  <div>
                    <span>实际时间</span>
                    <strong>{{ formatDateTime(row.actualPublishAt) }}</strong>
                  </div>
                  <div>
                    <span>偏差</span>
                    <strong>{{ formatDeviation(row.deviationMinutes) }}</strong>
                  </div>
                  <div>
                    <span>来源</span>
                    <strong>{{ row.dataSourceLabel }}</strong>
                  </div>
                  <div>
                    <span>浏览</span>
                    <strong>{{ row.impressions ?? '—' }}</strong>
                  </div>
                  <div>
                    <span>点赞</span>
                    <strong>{{ row.likes ?? '—' }}</strong>
                  </div>
                  <div>
                    <span>评论</span>
                    <strong>{{ row.comments ?? '—' }}</strong>
                  </div>
                  <div>
                    <span>收藏</span>
                    <strong>{{ row.collects ?? '—' }}</strong>
                  </div>
                  <div>
                    <span>转发</span>
                    <strong>{{ row.shares ?? '—' }}</strong>
                  </div>
                </div>

                <div v-if="decisionLoading.includes(row.scheduleId)" class="chain-status">
                  正在还原推荐依据…
                </div>
                <div v-else-if="decisionErrors[row.scheduleId]" class="chain-status">
                  {{ decisionErrors[row.scheduleId] }}
                </div>
                <div v-else-if="decisions[row.scheduleId]" class="chain">
                  <ol class="chain-steps">
                    <li>
                      <em>1</em>
                      <div>
                        <span>内容适配</span>
                        <strong>{{ decisions[row.scheduleId].content.contentTypeName }}</strong>
                        <small>
                          {{
                            decisions[row.scheduleId].content.modelName ||
                            `规则分类 · ${decisions[row.scheduleId].content.wordCount ?? 0} 字`
                          }}
                        </small>
                      </div>
                    </li>
                    <li>
                      <em>2</em>
                      <div>
                        <span>活跃度分析</span>
                        <strong>
                          {{ decisions[row.scheduleId].analysis.weekdayName }}
                          {{ String(decisions[row.scheduleId].analysis.hour).padStart(2, '0') }}:00
                        </strong>
                        <small>
                          账号样本 {{ decisions[row.scheduleId].analysis.accountSampleCount }} 条 ·
                          {{ decisions[row.scheduleId].analysis.window.label }}
                        </small>
                      </div>
                    </li>
                    <li>
                      <em>3</em>
                      <div>
                        <span>加权打分</span>
                        <strong>{{ decisions[row.scheduleId].analysis.score }}</strong>
                        <small>
                          当日最优
                          {{
                            String(decisions[row.scheduleId].analysis.bestHour).padStart(2, '0')
                          }}:00 （{{ decisions[row.scheduleId].analysis.bestHourScore }}）
                        </small>
                      </div>
                    </li>
                    <li>
                      <em>4</em>
                      <div>
                        <span>采纳与效果</span>
                        <strong>{{ decisions[row.scheduleId].decision.timeSourceLabel }}</strong>
                        <small>
                          实测互动率
                          {{
                            decisions[row.scheduleId].result.engagementRate !== null
                              ? `${decisions[row.scheduleId].result.engagementRate}%`
                              : '—'
                          }}
                        </small>
                      </div>
                    </li>
                  </ol>

                  <div class="chain-body">
                    <table class="chain-table">
                      <thead>
                        <tr>
                          <th>打分维度</th>
                          <th>权重</th>
                          <th>原始分</th>
                          <th>贡献分</th>
                          <th>说明</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr
                          v-for="item in decisions[row.scheduleId].analysis.components"
                          :key="item.type"
                        >
                          <td>{{ item.label }}</td>
                          <td>{{ percent(item.weight) }}</td>
                          <td>{{ item.rawScore }}</td>
                          <td class="chain-contrib">{{ item.contribution }}</td>
                          <td class="chain-desc">{{ item.description }}</td>
                        </tr>
                      </tbody>
                    </table>

                    <div class="chain-chart">
                      <div class="chain-chart-head">
                        <span>{{ decisions[row.scheduleId].analysis.weekdayName }}全天得分</span>
                        <i class="chain-legend">
                          <b class="picked" />本次 <b class="best" />最优
                        </i>
                      </div>
                      <ChartPanel
                        :option="hourlyOption(decisions[row.scheduleId])"
                        height="150px"
                      />
                    </div>
                  </div>

                  <p class="chain-note">{{ decisions[row.scheduleId].explainNotice }}</p>
                </div>
              </td>
            </tr>
          </template>
          <tr v-if="!records.length">
            <td colspan="5" class="empty">暂无数据</td>
          </tr>
        </tbody>
      </table>
    </section>
  </section>
</template>

<style scoped>
.review-panel {
  margin-top: 8px;
  background: #fff;
  border: 1px solid #e8eaed;
  border-radius: 16px;
  overflow: hidden;
}

.review-kpis {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0;
  border-bottom: 1px solid #eef0f3;
}

.review-kpis > div {
  padding: 18px 20px;
  border-right: 1px solid #eef0f3;
}

.review-kpis > div:last-child {
  border-right: none;
}

.review-kpis span {
  display: block;
  color: #8b93a1;
  font-size: 12px;
  letter-spacing: 0.01em;
}

.review-kpis strong {
  display: block;
  margin-top: 6px;
  color: #111827;
  font-size: 24px;
  font-weight: 600;
  letter-spacing: -0.02em;
}

.review-kpi-accent {
  grid-column: span 5;
  border-top: 1px solid #eef0f3;
  border-right: none !important;
  background: #f8fafc;
}

.review-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #6b7280;
  font-size: 12px;
  cursor: pointer;
  user-select: none;
}

.review-toggle input {
  accent-color: #2563eb;
  cursor: pointer;
}

.review-warning {
  margin: -4px 0 12px;
  border-radius: 8px;
  background: #fffbeb;
  color: #92400e;
  font-size: 11px;
  line-height: 1.6;
  padding: 8px 10px;
}

.review-charts {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  border-bottom: 1px solid #eef0f3;
}

.review-charts article {
  padding: 18px 16px 16px;
  border-right: 1px solid #eef0f3;
  min-width: 0;
}

.review-charts article:last-child {
  border-right: none;
}

.review-block {
  padding: 18px 20px 20px;
  border-bottom: 1px solid #eef0f3;
}

.review-block:last-child {
  border-bottom: none;
}

.review-block-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.review-block-head h3 {
  margin: 0;
  color: #111827;
  font-size: 15px;
  font-weight: 600;
}

.review-legend {
  display: flex;
  gap: 14px;
  color: #8b93a1;
  font-size: 12px;
}

.review-legend span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.dot.rec {
  background: #2563eb;
}

.dot.custom {
  background: #94a3b8;
}

.review-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.review-table th,
.review-table td {
  padding: 11px 10px;
  text-align: left;
  border-bottom: 1px solid #f1f3f5;
  white-space: nowrap;
}

.review-table th {
  color: #8b93a1;
  font-weight: 500;
  font-size: 12px;
}

.review-table tbody tr:last-child td {
  border-bottom: none;
}

.title-cell {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #111827;
  font-weight: 500;
}

.pill-rec,
.pill-custom {
  display: inline-block;
  border-radius: 999px;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 600;
}

.pill-rec {
  background: #eff6ff;
  color: #2563eb;
}

.pill-custom {
  background: #f3f4f6;
  color: #6b7280;
}

.expand-btn {
  width: 24px;
  height: 24px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
  color: #6b7280;
  cursor: pointer;
  line-height: 1;
}

.expand-row td {
  background: #fafbfc;
  padding: 0 !important;
}

.expand-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
  padding: 14px 12px;
}

.expand-grid span {
  display: block;
  color: #8b93a1;
  font-size: 11px;
}

.expand-grid strong {
  display: block;
  margin-top: 3px;
  color: #111827;
  font-size: 12px;
  font-weight: 600;
}

.empty {
  text-align: center;
  color: #8b93a1;
  padding: 28px !important;
}

.chain-status {
  padding: 0 12px 14px;
  color: #8b93a1;
  font-size: 12px;
}

.chain {
  border-top: 1px solid #eef0f3;
  padding: 14px 12px 16px;
}

.chain-steps {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin: 0 0 14px;
  padding: 0;
  list-style: none;
}

.chain-steps li {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  border: 1px solid #eef0f3;
  border-radius: 10px;
  background: #fff;
  padding: 10px 12px;
  min-width: 0;
}

.chain-steps em {
  flex: none;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #eff6ff;
  color: #2563eb;
  font-size: 11px;
  font-style: normal;
  font-weight: 600;
  line-height: 18px;
  text-align: center;
}

.chain-steps span {
  display: block;
  color: #8b93a1;
  font-size: 11px;
}

.chain-steps strong {
  display: block;
  margin-top: 2px;
  color: #111827;
  font-size: 13px;
  font-weight: 600;
}

.chain-steps small {
  display: block;
  margin-top: 2px;
  color: #8b93a1;
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chain-body {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}

.chain-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.chain-table th,
.chain-table td {
  padding: 8px 8px;
  text-align: left;
  border-bottom: 1px solid #f1f3f5;
}

.chain-table th {
  color: #8b93a1;
  font-weight: 500;
  font-size: 11px;
}

.chain-table tbody tr:last-child td {
  border-bottom: none;
}

.chain-contrib {
  color: #2563eb;
  font-weight: 600;
}

.chain-desc {
  color: #667085;
  white-space: normal;
  min-width: 200px;
}

.chain-chart-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: #8b93a1;
  font-size: 11px;
}

.chain-legend {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-style: normal;
}

.chain-legend b {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 2px;
}

.chain-legend b.picked {
  background: #2563eb;
}

.chain-legend b.best {
  margin-left: 6px;
  background: #93c5fd;
}

.chain-note {
  margin: 12px 0 0;
  color: #8b93a1;
  font-size: 11px;
  line-height: 1.6;
}

@media (max-width: 1100px) {
  .chain-steps {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .chain-body {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 900px) {
  .review-kpis {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .review-kpi-accent {
    grid-column: span 2;
  }

  .review-kpis > div {
    border-bottom: 1px solid #eef0f3;
  }

  .review-kpi-accent {
    grid-column: span 2;
  }

  .review-charts {
    grid-template-columns: 1fr;
  }

  .review-charts article {
    border-right: none;
    border-bottom: 1px solid #eef0f3;
  }

  .review-charts article:last-child {
    border-bottom: none;
  }

  .expand-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
