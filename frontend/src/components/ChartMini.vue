<script setup lang="ts">
import * as echarts from 'echarts'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useResizeObserver } from '@vueuse/core'

const props = defineProps<{ option: unknown }>()
const el = ref<HTMLElement>()
let chart: echarts.ECharts | undefined

function render() {
  if (!el.value) return
  if (!chart) chart = echarts.init(el.value)
  chart.setOption(props.option as echarts.EChartsOption, true)
  chart.resize()
}

onMounted(() => nextTick(render))
watch(() => props.option, () => nextTick(render), { deep: true })
useResizeObserver(el, () => chart?.resize())
onBeforeUnmount(() => chart?.dispose())
</script>

<template>
  <div ref="el" class="chart-mini-root" />
</template>

<style scoped>
.chart-mini-root {
  width: 100%;
  height: 100%;
}
</style>
