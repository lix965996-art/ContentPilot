<script setup lang="ts">
defineProps<{ eyebrow?: string; title: string; description?: string }>()
</script>

<template>
  <header v-if="$slots.default" class="page-header" :aria-label="title">
    <div class="flex shrink-0 items-center gap-2"><slot /></div>
  </header>
</template>
