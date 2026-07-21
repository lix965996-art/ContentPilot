<script setup lang="ts">
import * as echarts from 'echarts'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useResizeObserver } from '@vueuse/core'

const props = defineProps<{ option: unknown; height?: string }>()
const el = ref<HTMLElement>()
let chart: echarts.ECharts | undefined
onMounted(() => {
  if (el.value) {
    chart = echarts.init(el.value)
    chart.setOption(props.option as echarts.EChartsOption)
  }
})
watch(
  () => props.option,
  (value) => chart?.setOption(value as echarts.EChartsOption, true),
  { deep: true },
)
useResizeObserver(el, () => chart?.resize())
onBeforeUnmount(() => chart?.dispose())
</script>
<template><div ref="el" :style="{ height: height || '280px' }" /></template>
