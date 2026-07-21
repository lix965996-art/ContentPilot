<script setup lang="ts">
import { CheckCircle2, X } from 'lucide-vue-next'
defineProps<{ message: string; visible: boolean }>()
defineEmits<{ close: [] }>()
</script>

<template>
  <Transition name="toast">
    <div v-if="visible" class="app-toast" role="status">
      <CheckCircle2 :size="17" /><span>{{ message }}</span
      ><button aria-label="关闭" @click="$emit('close')"><X :size="14" /></button>
    </div>
  </Transition>
</template>
