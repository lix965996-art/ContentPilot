<script setup lang="ts">
withDefaults(
  defineProps<{
    compact?: boolean
    inverse?: boolean
    showSubtitle?: boolean
  }>(),
  {
    compact: false,
    inverse: false,
    showSubtitle: false,
  },
)
</script>

<template>
  <div class="brand-mark" aria-label="ContentPilot 多平台内容运营工作台">
    <span class="brand-symbol" aria-hidden="true">CP</span>
    <div v-if="!compact" class="min-w-0">
      <div :class="inverse ? 'text-white' : 'text-ink'" class="brand-name">ContentPilot</div>
      <div
        v-if="showSubtitle"
        :class="inverse ? 'text-slate-400' : 'text-muted'"
        class="brand-subtitle"
      >
        多平台内容运营工作台
      </div>
    </div>
  </div>
</template>
