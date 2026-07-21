<script setup lang="ts">
defineProps<{ modelValue: boolean; title: string; size?: string }>()
defineEmits<{ 'update:modelValue': [value: boolean] }>()
</script>
<template>
  <el-drawer
    :model-value="modelValue"
    :title="title"
    :size="size || '460px'"
    @update:model-value="$emit('update:modelValue', $event)"
    ><slot
  /></el-drawer>
</template>
