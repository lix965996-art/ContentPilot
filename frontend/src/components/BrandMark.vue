<script setup lang="ts">
import logoUrl from '@/assets/contentpilot-logo.png'

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
    <span class="brand-image-frame" :class="{ 'is-compact': compact }" aria-hidden="true">
      <img :src="logoUrl" alt="" />
    </span>
    <span v-if="showSubtitle && !compact" class="brand-subtitle">多平台内容运营工作台</span>
  </div>
</template>
