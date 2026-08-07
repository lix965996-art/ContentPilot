<script setup lang="ts">
import { computed } from 'vue'
import ChartPanel from '@/components/ChartPanel.vue'
import type { ActivityCurvePoint } from '@/types/business'

const props = defineProps<{
  curve: ActivityCurvePoint[]
  highlightHour?: number
}>()

const option = computed(() => ({
  grid: { left: 36, right: 12, top: 24, bottom: 28 },
  tooltip: { trigger: 'axis' },
  xAxis: {
    type: 'category',
    data: props.curve.map((item) => item.time),
    axisLabel: { interval: 1, fontSize: 10 },
  },
  yAxis: { type: 'value', min: 0, max: 100, axisLabel: { fontSize: 10 } },
  series: [
    {
      type: 'bar',
      data: props.curve.map((item) => ({
        value: Math.max(item.platformPrior, item.accountHistory || 0, item.publicBaseline || 0),
        itemStyle: {
          color: item.hour === props.highlightHour ? '#2563eb' : '#94a3b8',
        },
      })),
      barMaxWidth: 18,
    },
  ],
}))
</script>

<template>
  <ChartPanel :option="option" height="220px" />
</template>
