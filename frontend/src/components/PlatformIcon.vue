<script setup lang="ts">
import { computed } from 'vue'
import type { Platform } from '@/types/business'

const props = withDefaults(defineProps<{ platform: Platform; size?: 'sm' | 'md' }>(), {
  size: 'md',
})
const config = computed(
  () =>
    ({
      WEIBO: { label: '微', className: 'is-weibo' },
      XIAOHONGSHU: { label: '红', className: 'is-xiaohongshu' },
      WECHAT_OFFICIAL: { label: '微', className: 'is-wechat' },
    })[props.platform],
)
</script>

<template>
  <span class="platform-icon" :class="[config.className, `is-${size}`]" :title="platform">
    {{ config.label }}
  </span>
</template>
