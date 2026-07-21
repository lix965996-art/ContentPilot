<script setup lang="ts">
defineProps<{ loading?: boolean; empty?: boolean }>()
</script>
<template>
  <section class="data-surface" :class="{ 'is-loading': loading }">
    <slot /><slot v-if="empty" name="empty" />
  </section>
</template>
