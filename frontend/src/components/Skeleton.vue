<script setup lang="ts">
withDefaults(defineProps<{ lines?: number }>(), { lines: 3 })
</script>

<template>
  <div class="app-skeleton" aria-label="正在加载">
    <i v-for="line in lines" :key="line" :style="{ width: `${100 - (line - 1) * 12}%` }" />
  </div>
</template>
