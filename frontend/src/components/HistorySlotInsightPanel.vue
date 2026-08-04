<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import ChartPanel from '@/components/ChartPanel.vue'
import type { ActivityAnalysis } from '@/types/business'
import { AXIS_STYLE, CHART_COLORS, tooltipStyle } from '@/config/echartsTheme'

export interface RankedSlot {
  rank: number
  dayOfWeek: number
  dayName: string
  hour: number
  time: string
  sampleCount: number
  score: number
  displayScore: number
  confidence: 'HIGH' | 'MEDIUM' | 'LOW'
  confidenceLabel: string
}

const props = defineProps<{
  analysis?: ActivityAnalysis
  loading?: boolean
  canSchedule?: boolean
}>()

const emit = defineEmits<{
  recalculate: []
}>()

const router = useRouter()
const WEEKDAY_NAMES = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

const activeSlot = ref<RankedSlot | null>(null)
const selectedDayOfWeek = ref(0)

function confidenceOf(count: number): RankedSlot['confidence'] {
  if (count > 30) return 'HIGH'
  if (count > 10) return 'MEDIUM'
  return 'LOW'
}

function confidenceLabel(level: RankedSlot['confidence']) {
  return ({ HIGH: '高', MEDIUM: '中', LOW: '低' } as const)[level]
}

const maxScore = computed(() => {
  const scores = (props.analysis?.heatmap || [])
    .filter((item) => item.score > 0)
    .map((item) => item.score)
  return Math.max(...scores, 1)
})

function toRankedSlot(
  item: {
    dayOfWeek: number
    dayName: string
    hour: number
    time: string
    sampleCount: number
    score: number
  },
  rank: number,
): RankedSlot {
  const confidence = confidenceOf(item.sampleCount)
  return {
    rank,
    dayOfWeek: item.dayOfWeek,
    dayName: item.dayName,
    hour: item.hour,
    time: item.time,
    sampleCount: item.sampleCount,
    score: item.score,
    displayScore: Math.round((item.score / maxScore.value) * 100),
    confidence,
    confidenceLabel: confidenceLabel(confidence),
  }
}

const primaryRecommendation = computed(() => {
  const top = props.analysis?.topSlots?.[0]
  if (!top) return null
  return toRankedSlot(top, 1)
})

const alternativeSlots = computed(() =>
  (props.analysis?.topSlots || [])
    .slice(1, 4)
    .map((item, index) => toRankedSlot(item, index + 2)),
)

const accountShare = computed(() => {
  const total = props.analysis?.sampleCount || 0
  if (!total) return 0
  return Math.round(((props.analysis?.accountSampleCount || 0) / total) * 100)
})

const baselineShare = computed(() => {
  const total = props.analysis?.sampleCount || 0
  if (!total) return 0
  return Math.round(((props.analysis?.baselineSampleCount || 0) / total) * 100)
})

const accountSampleCount = computed(() => props.analysis?.accountSampleCount || 0)
const baselineSampleCount = computed(() => props.analysis?.baselineSampleCount || 0)

const weekdayBarOption = computed(() => {
  const weekday = props.analysis?.weekday || []
  const max = Math.max(...weekday.map((row) => row.score), 1)
  const selected = selectedDayOfWeek.value

  return {
    grid: { left: 36, right: 12, top: 28, bottom: 28 },
    tooltip: {
      ...tooltipStyle(),
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params: Array<{ dataIndex: number; value: number }>) => {
        const row = weekday[params[0]?.dataIndex]
        if (!row) return ''
        return `${row.name}<br/>得分 ${params[0].value}<br/>样本 ${row.sampleCount}`
      },
    },
    xAxis: {
      type: 'category',
      data: weekday.map((row) => row.name),
      axisLabel: { fontSize: 11, color: CHART_COLORS.muted },
      axisLine: { lineStyle: { color: CHART_COLORS.line } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      ...AXIS_STYLE,
    },
    series: [
      {
        type: 'bar',
        barMaxWidth: 28,
        label: {
          show: true,
          position: 'top',
          fontSize: 10,
          color: '#667085',
          formatter: (param: { value: number }) => (param.value > 0 ? String(param.value) : ''),
        },
        data: weekday.map((row, index) => ({
          value: Math.round((row.score / max) * 100),
          itemStyle: {
            color: index === selected ? '#2563EB' : '#BFDBFE',
            borderRadius: [4, 4, 0, 0],
          },
        })),
      },
    ],
  }
})

const sampleMixPieOption = computed(() => {
  const data = [
    { name: '账号历史', value: accountSampleCount.value },
    { name: '公开样本', value: baselineSampleCount.value },
  ].filter((item) => item.value > 0)

  return {
    color: ['#2563EB', '#BFDBFE'],
    tooltip: {
      ...tooltipStyle(),
      trigger: 'item',
      formatter: (p: { name: string; value: number; percent: number }) =>
        `${p.name}<br/><b>${p.value.toLocaleString()}</b> 条 · ${p.percent}%`,
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
        radius: ['52%', '72%'],
        center: ['50%', '46%'],
        avoidLabelOverlap: true,
        itemStyle: {
          borderColor: '#fff',
          borderWidth: 2,
        },
        label: {
          show: true,
          formatter: '{d}%',
          color: '#475467',
          fontSize: 11,
        },
        labelLine: {
          length: 8,
          length2: 6,
          lineStyle: { color: '#d0d5dd' },
        },
        data,
      },
    ],
  }
})

const dayHourRows = computed(() => {
  const heatmap = props.analysis?.heatmap || []
  const day = selectedDayOfWeek.value
  const rows = Array.from({ length: 24 }, (_, hour) => {
    const cell = heatmap.find((item) => item.dayOfWeek === day && item.hour === hour)
    const score = cell?.score ?? 0
    return {
      hour,
      time: `${String(hour).padStart(2, '0')}:00`,
      score,
      sampleCount: cell?.sampleCount ?? 0,
      displayScore: score > 0 ? Math.round((score / maxScore.value) * 100) : 0,
    }
  })
  const topHours = [...rows]
    .filter((row) => row.score > 0)
    .sort((left, right) => right.score - left.score || right.sampleCount - left.sampleCount)
    .slice(0, 3)
    .map((row) => row.hour)
  return { rows, topHours }
})

const hourlyBarOption = computed(() => {
  const { rows, topHours } = dayHourRows.value
  const slot = activeSlot.value
  const highlightHour =
    slot && slot.dayOfWeek === selectedDayOfWeek.value ? slot.hour : topHours[0] ?? -1

  return {
    grid: { left: 40, right: 8, top: 28, bottom: 24 },
    tooltip: {
      ...tooltipStyle(),
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params: Array<{ dataIndex: number }>) => {
        const row = rows[params[0]?.dataIndex]
        if (!row) return ''
        return `${WEEKDAY_NAMES[selectedDayOfWeek.value]} ${row.time}<br/>得分 ${row.displayScore}<br/>样本 ${row.sampleCount}`
      },
    },
    xAxis: {
      type: 'category',
      data: rows.map((row) => row.time.slice(0, 2)),
      axisLabel: { interval: 1, fontSize: 10, color: CHART_COLORS.muted },
      axisLine: { lineStyle: { color: CHART_COLORS.line } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      max: 100,
      ...AXIS_STYLE,
    },
    series: [
      {
        type: 'bar',
        barMaxWidth: 16,
        label: {
          show: true,
          position: 'top',
          fontSize: 10,
          color: '#667085',
          formatter: (param: { value: number }) => (param.value > 0 ? String(param.value) : ''),
        },
        data: rows.map((row) => ({
          value: row.displayScore,
          itemStyle: {
            color:
              row.hour === highlightHour
                ? '#2563EB'
                : topHours.includes(row.hour)
                  ? '#93C5FD'
                  : '#BFDBFE',
            borderRadius: [4, 4, 0, 0],
          },
          label: {
            color: row.hour === highlightHour ? '#2563EB' : '#667085',
            fontWeight: row.hour === highlightHour ? 600 : 400,
          },
        })),
      },
    ],
  }
})

function selectDay(day: number) {
  selectedDayOfWeek.value = day
}

function selectSlot(slot: RankedSlot) {
  activeSlot.value = slot
  selectedDayOfWeek.value = slot.dayOfWeek
}

function pickFirstAlternative() {
  const alt = alternativeSlots.value[0]
  if (!alt) {
    ElMessage.info('暂无备选时段')
    return
  }
  selectSlot(alt)
}

function joinSchedule() {
  if (!props.canSchedule) {
    ElMessage.warning('需要运营者权限才能加入排期')
    return
  }
  const slot = activeSlot.value
  if (!slot) return
  router.push({
    name: 'calendar',
    query: {
      create: '1',
      suggestDay: String(slot.dayOfWeek),
      suggestHour: String(slot.hour),
    },
  })
}

function handleRecalculate() {
  emit('recalculate')
}

watch(
  primaryRecommendation,
  (slot) => {
    if (!slot) {
      activeSlot.value = null
      return
    }
    if (!activeSlot.value) {
      activeSlot.value = slot
      selectedDayOfWeek.value = slot.dayOfWeek
    }
  },
  { immediate: true },
)

watch(
  () => props.analysis,
  () => {
    const slot = primaryRecommendation.value
    if (slot) {
      activeSlot.value = slot
      selectedDayOfWeek.value = slot.dayOfWeek
    }
  },
)
</script>

<template>
  <section class="slot-panel">
    <div v-if="loading" class="slot-empty">加载中…</div>
    <div v-else-if="!primaryRecommendation" class="slot-empty">暂无可用时段</div>

    <template v-else-if="activeSlot">
      <header class="slot-hero">
        <div>
          <p class="slot-label">推荐发布时间</p>
          <p class="slot-time">{{ activeSlot.dayName }} {{ activeSlot.time }}</p>
          <div class="slot-meta">
            <span>置信度 {{ activeSlot.confidenceLabel }}</span>
            <span>样本 {{ activeSlot.sampleCount }}</span>
            <span>账号 {{ accountShare }}% · 公开 {{ baselineShare }}%</span>
          </div>
        </div>
        <div class="slot-actions">
          <el-button type="primary" :disabled="!canSchedule" @click="joinSchedule">
            加入排期
          </el-button>
          <el-button :disabled="!alternativeSlots.length" @click="pickFirstAlternative">
            备选时间
          </el-button>
          <el-button text @click="handleRecalculate">重新计算</el-button>
        </div>
      </header>

      <nav class="slot-weekdays">
        <button
          v-for="(name, day) in WEEKDAY_NAMES"
          :key="name"
          type="button"
          :class="{ active: selectedDayOfWeek === day }"
          @click="selectDay(day)"
        >
          {{ name }}
        </button>
      </nav>

      <section class="slot-chart">
        <h3>{{ WEEKDAY_NAMES[selectedDayOfWeek] }} · 24 小时</h3>
        <ChartPanel :option="hourlyBarOption" height="200px" />
      </section>

      <section class="slot-charts-row">
        <article>
          <h3>星期对比</h3>
          <ChartPanel :option="weekdayBarOption" height="200px" />
        </article>
        <article>
          <h3>样本构成</h3>
          <ChartPanel :option="sampleMixPieOption" height="200px" />
        </article>
      </section>

      <section class="slot-alts">
        <h3>备选时段</h3>
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>时间</th>
              <th>得分</th>
              <th>样本</th>
              <th />
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in alternativeSlots" :key="`${row.dayOfWeek}-${row.hour}`">
              <td>{{ row.rank }}</td>
              <td>{{ row.dayName }} {{ row.time }}</td>
              <td>{{ row.displayScore }}</td>
              <td>{{ row.sampleCount }}</td>
              <td>
                <button type="button" class="link" @click="selectSlot(row)">选择</button>
              </td>
            </tr>
            <tr v-if="!alternativeSlots.length">
              <td colspan="5" class="slot-empty-cell">暂无备选</td>
            </tr>
          </tbody>
        </table>
      </section>
    </template>
  </section>
</template>

<style scoped>
.slot-panel {
  grid-column: span 12;
  background: #fff;
  border: 1px solid #e8eaed;
  border-radius: 16px;
  overflow: hidden;
}

.slot-empty {
  padding: 48px 20px;
  color: #8b93a1;
  font-size: 13px;
  text-align: center;
}

.slot-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding: 22px 24px 18px;
}

.slot-label {
  margin: 0;
  color: #8b93a1;
  font-size: 12px;
}

.slot-time {
  margin: 6px 0 10px;
  color: #111827;
  font-size: 34px;
  font-weight: 700;
  letter-spacing: -0.03em;
  line-height: 1.1;
}

.slot-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  color: #6b7280;
  font-size: 12px;
}

.slot-actions {
  display: flex;
  flex-shrink: 0;
  flex-wrap: wrap;
  gap: 8px;
}

.slot-weekdays {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 6px;
  padding: 0 24px 14px;
  border-bottom: 1px solid #f1f3f5;
}

.slot-weekdays button {
  border: none;
  border-radius: 10px;
  background: transparent;
  color: #6b7280;
  font-size: 13px;
  font-weight: 500;
  padding: 10px 0;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}

.slot-weekdays button:hover {
  background: #f5f7fa;
  color: #111827;
}

.slot-weekdays button.active {
  background: #eff6ff;
  color: #2563eb;
}

.slot-chart,
.slot-alts {
  padding: 16px 24px 20px;
}

.slot-charts-row {
  display: grid;
  grid-template-columns: 1.2fr 0.8fr;
  gap: 0;
  border-top: 1px solid #f1f3f5;
}

.slot-charts-row article {
  padding: 16px 24px 20px;
}

.slot-charts-row article + article {
  border-left: 1px solid #f1f3f5;
}

.slot-alts {
  border-top: 1px solid #f1f3f5;
}

.slot-chart h3,
.slot-charts-row h3,
.slot-alts h3 {
  margin: 0 0 10px;
  color: #111827;
  font-size: 14px;
  font-weight: 600;
}

.slot-alts table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.slot-alts th,
.slot-alts td {
  padding: 10px 8px;
  text-align: left;
  border-bottom: 1px solid #f1f3f5;
}

.slot-alts th {
  color: #8b93a1;
  font-size: 12px;
  font-weight: 500;
}

.slot-alts tbody tr:last-child td {
  border-bottom: none;
}

.link {
  border: none;
  background: transparent;
  color: #2563eb;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  padding: 0;
}

.slot-empty-cell {
  text-align: center;
  color: #8b93a1;
}

@media (max-width: 900px) {
  .slot-charts-row {
    grid-template-columns: 1fr;
  }

  .slot-charts-row article + article {
    border-left: none;
    border-top: 1px solid #f1f3f5;
  }
}

@media (max-width: 768px) {
  .slot-hero {
    flex-direction: column;
  }

  .slot-time {
    font-size: 28px;
  }
}
</style>
