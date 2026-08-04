/** Shared ECharts visual tokens — aligned with ContentPilot design system. */
export const CHART_COLORS = {
  brand: '#2563EB',
  brandLight: '#93C5FD',
  accent: '#7C3AED',
  accentLight: '#C4B5FD',
  success: '#16A34A',
  warning: '#F59E0B',
  ink: '#172033',
  muted: '#667085',
  line: '#E5E7EB',
  grid: '#F1F5F9',
  canvas: '#F8FAFC',
}

export const CHART_PALETTE = [
  CHART_COLORS.brand,
  CHART_COLORS.accent,
  '#0EA5E9',
  CHART_COLORS.success,
  CHART_COLORS.warning,
  '#64748B',
]

export const HEATMAP_GRADIENT = ['#F8FAFC', '#DBEAFE', '#60A5FA', '#2563EB', '#1E3A8A']

export const AXIS_STYLE = {
  axisLine: { show: false },
  axisTick: { show: false },
  axisLabel: { color: CHART_COLORS.muted, fontSize: 11 },
  splitLine: { lineStyle: { color: CHART_COLORS.grid, type: 'dashed' as const } },
}

export function tooltipStyle() {
  return {
    backgroundColor: 'rgba(255,255,255,0.96)',
    borderColor: CHART_COLORS.line,
    borderWidth: 1,
    padding: [10, 14],
    textStyle: { color: CHART_COLORS.ink, fontSize: 12 },
    extraCssText: 'box-shadow: 0 8px 24px rgba(16,24,40,0.08); border-radius: 10px;',
  }
}

export function linearGradient(
  from: string,
  to: string,
  direction: 'vertical' | 'horizontal' = 'vertical',
) {
  return {
    type: 'linear' as const,
    x: 0,
    y: 0,
    x2: direction === 'horizontal' ? 1 : 0,
    y2: direction === 'vertical' ? 1 : 0,
    colorStops: [
      { offset: 0, color: from },
      { offset: 1, color: to },
    ],
  }
}
