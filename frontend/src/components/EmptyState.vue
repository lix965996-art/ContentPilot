<script setup lang="ts">
defineProps<{ title: string; description?: string }>()
</script>
<template>
  <div class="empty-state">
    <slot name="icon" />
    <p>{{ title }}</p>
    <span v-if="description">{{ description }}</span
    ><slot />
  </div>
</template>
