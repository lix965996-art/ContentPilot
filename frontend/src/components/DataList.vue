<script setup lang="ts">
defineProps<{ loading?: boolean; empty?: boolean }>()
</script>

<template>
  <section class="data-list" :aria-busy="loading">
    <div v-if="loading" class="data-list-skeleton" aria-label="正在加载">
      <span v-for="item in 4" :key="item" />
    </div>
    <slot v-else />
    <slot v-if="!loading && empty" name="empty" />
  </section>
</template>
