<script setup lang="ts">
import { computed } from 'vue'
import type { Platform, RecommendationPlanRow } from '@/types/business'
import { platformNames } from '@/types/business'

const props = defineProps<{
  modelValue: boolean
  rows: RecommendationPlanRow[]
  scheduling: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  confirm: []
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})

function formatTime(value: string) {
  return new Date(value).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
</script>

<template>
  <el-dialog v-model="visible" title="确认生成跨平台排期" width="min(720px, 92vw)">
    <p class="lead">将为以下平台创建真实 publish_schedule 记录，并跳转日历高亮本次任务。</p>
    <el-table :data="rows" size="small">
      <el-table-column label="平台" width="120">
        <template #default="{ row }">{{ platformNames[row.platform as Platform] }}</template>
      </el-table-column>
      <el-table-column prop="accountName" label="账号" min-width="120" />
      <el-table-column label="排期时间" min-width="160">
        <template #default="{ row }">{{ formatTime(row.selectedAt) }}</template>
      </el-table-column>
      <el-table-column label="时间来源" width="100">
        <template #default="{ row }">{{ row.timeSource }}</template>
      </el-table-column>
      <el-table-column label="冲突" min-width="120">
        <template #default="{ row }">{{ row.conflictMessage || '无冲突' }}</template>
      </el-table-column>
    </el-table>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="scheduling" @click="emit('confirm')">
        一键生成跨平台排期
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.lead {
  margin: 0 0 12px;
  color: var(--sf-muted, #667085);
  font-size: 13px;
}
</style>
