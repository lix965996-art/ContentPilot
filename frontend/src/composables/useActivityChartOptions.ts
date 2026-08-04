import type { ComputedRef } from 'vue'
import type { ActivityAnalysis } from '@/types/business'
import {
  AXIS_STYLE,
  CHART_COLORS,
  CHART_PALETTE,
  HEATMAP_GRADIENT,
  linearGradient,
  tooltipStyle,
} from '@/config/echartsTheme'

type AnalysisSource =
  | ComputedRef<ActivityAnalysis | undefined>
  | { value: ActivityAnalysis | undefined }

function rows(source: AnalysisSource) {
  return source.value
}

function shortSourceLabel(label: string) {
  return label
    .replace('（用户导入）', '')
    .replace('（非国内平台数据）', '')
    .replace('YouTube 公开样本', 'YouTube 公开')
}

export function buildSourcePieOption(
  sources: Array<{ label: string; count: number; sourceType?: string }>,
) {
  const total = sources.reduce((sum, item) => sum + item.count, 0)
  return {
    color: CHART_PALETTE,
    tooltip: {
      ...tooltipStyle(),
      trigger: 'item',
      formatter: (p: { name: string; value: number; percent: number }) =>
        `${p.name}<br/><b>${p.value.toLocaleString()}</b> 条 · ${p.percent}%`,
    },
    legend: {
      orient: 'vertical',
      right: 8,
      top: 'center',
      icon: 'circle',
      itemWidth: 8,
      itemHeight: 8,
      itemGap: 14,
      formatter: (name: string) => {
        const item = sources.find((row) => shortSourceLabel(row.label) === name)
        if (!item || !total) return name
        return `{name|${name}}  {val|${((item.count / total) * 100).toFixed(1)}%}`
      },
      textStyle: {
        rich: {
          name: { color: CHART_COLORS.ink, fontSize: 12, width: 100 },
          val: { color: CHART_COLORS.brand, fontSize: 12, fontWeight: 600 },
        },
      },
    },
    series: [
      {
        type: 'pie',
        radius: ['48%', '72%'],
        center: ['36%', '50%'],
        roseType: 'radius',
        itemStyle: {
          borderRadius: 8,
          borderColor: '#fff',
          borderWidth: 3,
        },
        label: { show: false },
        emphasis: {
          scale: true,
          scaleSize: 6,
          itemStyle: { shadowBlur: 16, shadowColor: 'rgba(37,99,235,0.18)' },
        },
        data: sources.map((item, index) => ({
          name: shortSourceLabel(item.label),
          value: item.count,
          itemStyle: {
            color: linearGradient(
              CHART_PALETTE[index % CHART_PALETTE.length],
              index % 2 ? CHART_COLORS.accentLight : CHART_COLORS.brandLight,
            ),
          },
        })),
      },
    ],
  }
}

export function buildWeekdayBarOption(source: AnalysisSource) {
  const weekday = rows(source)?.weekday || []
  const peak = Math.max(...weekday.map((item) => item.score), 1)
  const maxIndex = weekday.reduce(
    (best, row, index, arr) => (row.score > arr[best].score ? index : best),
    0,
  )
  return {
    tooltip: {
      ...tooltipStyle(),
      trigger: 'axis',
      formatter: (params: Array<{ name: string; value: number; dataIndex: number }>) => {
        const row = weekday[params[0]?.dataIndex]
        if (!row) return ''
        return `${row.name}<br/>活跃度 <b>${row.score}</b><br/>样本 ${row.sampleCount} 条`
      },
    },
    grid: { left: 8, right: 8, top: 16, bottom: 28, containLabel: true },
    xAxis: {
      type: 'category',
      data: weekday.map((item) => item.name),
      ...AXIS_STYLE,
      axisLabel: { color: CHART_COLORS.muted, fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      max: Math.ceil(peak * 1.15),
      ...AXIS_STYLE,
    },
    series: [
      {
        type: 'bar',
        barWidth: 28,
        data: weekday.map((item, index) => ({
          value: item.score,
          itemStyle: {
            borderRadius: [8, 8, 0, 0],
            color: linearGradient(
              index === maxIndex ? CHART_COLORS.accent : CHART_COLORS.brand,
              index === maxIndex ? '#ddd6fe' : CHART_COLORS.brandLight,
            ),
          },
        })),
        emphasis: { focus: 'series' },
      },
    ],
  }
}

export function buildHourlyAreaOption(source: AnalysisSource) {
  const hourly = rows(source)?.hourly || []
  const peak = Math.max(...hourly.map((item) => item.score), 1)
  return {
    tooltip: {
      ...tooltipStyle(),
      trigger: 'axis',
      formatter: (params: Array<{ name: string; value: number }>) =>
        `${params[0]?.name}<br/>活跃度 <b>${params[0]?.value}</b>`,
    },
    grid: { left: 8, right: 12, top: 20, bottom: 24, containLabel: true },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: hourly.map((item) => item.time),
      ...AXIS_STYLE,
      axisLabel: { interval: 3, color: CHART_COLORS.muted, fontSize: 10 },
    },
    yAxis: {
      type: 'value',
      min: Math.floor(Math.min(...hourly.map((item) => item.score)) * 0.92),
      max: Math.ceil(peak * 1.08),
      ...AXIS_STYLE,
    },
    series: [
      {
        type: 'line',
        smooth: 0.42,
        symbol: 'circle',
        symbolSize: 6,
        showSymbol: false,
        lineStyle: { color: CHART_COLORS.accent, width: 3 },
        itemStyle: { color: CHART_COLORS.accent, borderColor: '#fff', borderWidth: 2 },
        areaStyle: {
          color: linearGradient('rgba(124,58,237,0.32)', 'rgba(124,58,237,0.02)'),
        },
        markPoint: {
          symbol: 'pin',
          symbolSize: 42,
          label: { fontSize: 10, color: '#fff' },
          data: [
            { type: 'max', name: '峰值', itemStyle: { color: CHART_COLORS.accent } },
          ],
        },
        data: hourly.map((item) => item.score),
      },
    ],
  }
}

export function buildActivityHeatmapOption(source: AnalysisSource) {
  const heatmap = rows(source)?.heatmap || []
  const max = Math.max(1, ...heatmap.map((item) => item.score))
  const min = Math.min(...heatmap.filter((item) => item.score > 0).map((item) => item.score), max)
  return {
    tooltip: {
      ...tooltipStyle(),
      formatter: (params: { data: number[] }) => {
        const day = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][params.data[1]]
        return `${day} ${String(params.data[0]).padStart(2, '0')}:00<br/>活跃度 <b>${params.data[2]}</b>`
      },
    },
    grid: { left: 52, right: 16, top: 12, bottom: 56 },
    xAxis: {
      type: 'category',
      data: Array.from({ length: 24 }, (_, index) => `${index}`),
      axisLabel: { interval: 1, fontSize: 9, color: CHART_COLORS.muted },
      splitArea: { show: true, areaStyle: { color: ['#fff', '#fafbfc'] } },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'category',
      data: ['周一', '周二', '周三', '周四', '周五', '周六', '周日'],
      axisLabel: { fontSize: 11, color: CHART_COLORS.ink, fontWeight: 500 },
      splitArea: { show: true, areaStyle: { color: ['#fff', '#fafbfc'] } },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    visualMap: {
      min,
      max,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 4,
      itemWidth: 14,
      itemHeight: 120,
      text: ['高', '低'],
      textStyle: { color: CHART_COLORS.muted, fontSize: 10 },
      inRange: { color: HEATMAP_GRADIENT },
    },
    series: [
      {
        type: 'heatmap',
        data: heatmap.map((item) => [item.hour, item.dayOfWeek, item.score || '-']),
        label: { show: false },
        emphasis: {
          itemStyle: { shadowBlur: 8, shadowColor: 'rgba(37,99,235,0.25)' },
        },
        progressive: 0,
      },
    ],
  }
}

export function buildTopSlotsBarOption(source: AnalysisSource) {
  const slots = [...(rows(source)?.topSlots || [])].slice(0, 8).reverse()
  return {
    tooltip: {
      ...tooltipStyle(),
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params: Array<{ name: string; value: number }>) =>
        `${params[0]?.name}<br/>得分 <b>${params[0]?.value}</b>`,
    },
    grid: { left: 8, right: 24, top: 8, bottom: 8, containLabel: true },
    xAxis: {
      type: 'value',
      max: Math.ceil(Math.max(...slots.map((item) => item.score), 1) * 1.1),
      ...AXIS_STYLE,
    },
    yAxis: {
      type: 'category',
      data: slots.map((item) => `${item.dayName} ${item.time}`),
      axisLabel: { fontSize: 11, color: CHART_COLORS.ink, fontWeight: 500 },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series: [
      {
        type: 'bar',
        barWidth: 16,
        showBackground: true,
        backgroundStyle: { color: '#f1f5f9', borderRadius: 8 },
        itemStyle: {
          borderRadius: 8,
          color: linearGradient(CHART_COLORS.brand, CHART_COLORS.accent, 'horizontal'),
        },
        label: {
          show: true,
          position: 'right',
          color: CHART_COLORS.brand,
          fontWeight: 600,
          fontSize: 11,
        },
        data: slots.map((item) => item.score),
      },
    ],
  }
}

/** @deprecated Use buildWeekdayBarOption — radar looked too small with 0–100 scale. */
export function buildWeekdayRadarOption(source: AnalysisSource) {
  return buildWeekdayBarOption(source)
}
