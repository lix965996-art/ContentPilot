<script setup lang="ts">
withDefaults(
  defineProps<{
    compact?: boolean
    inverse?: boolean
  }>(),
  {
    compact: false,
    inverse: false,
  },
)
</script>

<template>
  <div class="flex items-center gap-3" aria-label="SocialFlow 内容运营系统">
    <div
      class="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-brand text-sm font-bold text-white shadow-sm"
      aria-hidden="true"
    >
      SF
    </div>
    <div v-if="!compact" class="min-w-0">
      <div
        :class="inverse ? 'text-white' : 'text-ink'"
        class="text-[15px] font-semibold tracking-tight"
      >
        SocialFlow
      </div>
      <div
        :class="inverse ? 'text-slate-400' : 'text-muted'"
        class="mt-0.5 text-[10px] tracking-[0.14em]"
      >
        内容运营系统
      </div>
    </div>
  </div>
</template>
