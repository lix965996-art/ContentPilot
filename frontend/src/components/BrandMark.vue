<script setup lang="ts">
import { Send } from 'lucide-vue-next'

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
  <div
    class="brand-mark"
    :class="{ 'has-subtitle': showSubtitle && !compact, 'is-inverse': inverse }"
    aria-label="ContentPilot 多平台内容运营工作台"
  >
    <span class="brand-symbol" aria-hidden="true">
      <Send :size="20" :stroke-width="1.8" />
    </span>
    <span v-if="!compact" class="brand-wordmark">
      <span class="brand-name">ContentPilot</span>
      <span v-if="showSubtitle" class="brand-subtitle">多平台内容运营工作台</span>
    </span>
  </div>
</template>
