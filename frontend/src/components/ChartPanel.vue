<script setup lang="ts">
import * as echarts from 'echarts'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useResizeObserver } from '@vueuse/core'

const props = defineProps<{ option: unknown; height?: string; loading?: boolean }>()
const el = ref<HTMLElement>()
let chart: echarts.ECharts | undefined

function renderChart() {
  if (!el.value || props.loading) return
  if (!chart) {
    chart = echarts.init(el.value)
  }
  chart.setOption(props.option as echarts.EChartsOption, true)
  chart.resize()
}

onMounted(() => {
  nextTick(renderChart)
})

watch(
  () => props.option,
  () => {
    nextTick(renderChart)
  },
  { deep: true },
)

watch(
  () => props.loading,
  (loading) => {
    if (!loading) {
      nextTick(renderChart)
    }
  },
)

useResizeObserver(el, () => chart?.resize())

onBeforeUnmount(() => chart?.dispose())
</script>

<template>
  <div ref="el" :style="{ height: height || '280px' }" />
</template>
