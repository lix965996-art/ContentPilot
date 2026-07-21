<script setup lang="ts">
defineProps<{ modelValue: boolean; title: string; message: string; danger?: boolean }>()
defineEmits<{ 'update:modelValue': [value: boolean]; confirm: [] }>()
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :title="title"
    width="400px"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <p class="confirm-copy">{{ message }}</p>
    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button :type="danger ? 'danger' : 'primary'" @click="$emit('confirm')">确认</el-button>
    </template>
  </el-dialog>
</template>
