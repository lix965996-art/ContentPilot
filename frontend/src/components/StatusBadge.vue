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
  RETRYING: '重试中',
  SUCCESS: '成功',
  PARTIAL_SUCCESS: '部分成功',
  DRAFT_CREATED: '已进入草稿箱',
  PUBLISH_SUBMITTED: '已提交发布',
  MANUAL_PUBLISHED: '人工发布完成',
  FAILED: '失败',
  REJECTED: '已拒绝',
  WAITING_MANUAL_CONFIRM: '待人工确认',
  CANCELLED: '已取消',
  FINISHED: '已结束',
  ACTIVE: '启用',
  DISABLED: '停用',
}
const tone = computed(() =>
  [
    'SUCCESS',
    'DRAFT_CREATED',
    'PUBLISH_SUBMITTED',
    'MANUAL_PUBLISHED',
    'APPROVED',
    'FINISHED',
    'ACTIVE',
  ].includes(props.status)
    ? 'success'
    : ['FAILED', 'DISABLED', 'REJECTED'].includes(props.status)
      ? 'danger'
      : ['RUNNING', 'RETRYING', 'GENERATED'].includes(props.status)
        ? 'primary'
        : ['WAITING_MANUAL_CONFIRM', 'PARTIAL_SUCCESS'].includes(props.status)
          ? 'warning'
          : 'neutral',
)
</script>
<template>
  <span class="status-badge" :data-tone="tone"><i />{{ labelMap[status] || status }}</span>
</template>
