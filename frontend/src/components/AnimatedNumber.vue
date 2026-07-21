<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'

const props = withDefaults(defineProps<{ value: number; duration?: number }>(), { duration: 420 })
const display = ref(0)
let frame = 0

watch(
  () => props.value,
  (next, previous = 0) => {
    window.cancelAnimationFrame(frame)
    const start = window.performance.now()
    const from = Number.isFinite(previous) ? previous : 0
    const draw = (now: number) => {
      const progress = Math.min((now - start) / props.duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      display.value = Math.round((from + (next - from) * eased) * 100) / 100
      if (progress < 1) frame = window.requestAnimationFrame(draw)
    }
    frame = window.requestAnimationFrame(draw)
  },
  { immediate: true },
)

onBeforeUnmount(() => window.cancelAnimationFrame(frame))
</script>

<template>{{ display }}</template>
