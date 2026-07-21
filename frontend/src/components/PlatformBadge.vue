<script setup lang="ts">
import PlatformIcon from '@/components/PlatformIcon.vue'
import type { Platform } from '@/types/business'
import { platformNames } from '@/types/business'
defineProps<{ platform: Platform; compact?: boolean }>()
</script>

<template>
  <span class="platform-badge"
    ><PlatformIcon :platform="platform" size="sm" />{{
      compact ? '' : platformNames[platform]
    }}</span
  >
</template>
