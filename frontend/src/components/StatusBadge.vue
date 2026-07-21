<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ status: string }>()
const labelMap: Record<string, string> = {
  DRAFT: '草稿',
  GENERATED: '已生成',
  APPROVED: '已审核',
  ARCHIVED: '已归档',
  PENDING: '待执行',
  RUNNING: '执行中',
  SUCCESS: '成功',
  MOCK_SUCCESS: '模拟成功',
  FAILED: '失败',
  WAITING_MANUAL_CONFIRM: '待人工确认',
  CANCELLED: '已取消',
  FINISHED: '已结束',
  ACTIVE: '启用',
  DISABLED: '停用',
}
const tone = computed(() =>
  ['SUCCESS', 'MOCK_SUCCESS', 'APPROVED', 'FINISHED', 'ACTIVE'].includes(props.status)
    ? 'success'
    : ['FAILED', 'DISABLED'].includes(props.status)
      ? 'danger'
      : ['RUNNING', 'GENERATED'].includes(props.status)
        ? 'primary'
        : ['WAITING_MANUAL_CONFIRM'].includes(props.status)
          ? 'warning'
          : 'neutral',
)
</script>
<template>
  <span class="status-badge" :data-tone="tone"><i />{{ labelMap[status] || status }}</span>
</template>
