import type { GenerationTask, Platform, Schedule } from '@/types/business'

export function generationOutcome(task: GenerationTask, success: string, platform?: Platform) {
  if (
    task.status === 'FAILED' ||
    (platform && task.platformStatusJson[platform]?.status === 'FAILED')
  ) {
    return {
      type: 'error' as const,
      message:
        task.platformStatusJson[platform!]?.error ||
        task.errorMessage ||
        '生成失败，请查看任务详情后重试',
    }
  }
  if (task.status === 'PARTIAL_SUCCESS')
    return { type: 'warning' as const, message: '部分平台生成成功，可单独重试失败平台' }
  if (task.status !== 'SUCCESS')
    return { type: 'info' as const, message: '任务仍在处理中，请查看任务状态' }
  return { type: 'success' as const, message: success }
}

export function publishOutcome(schedule: Schedule) {
  switch (schedule.status) {
    case 'FAILED':
      return {
        type: 'error' as const,
        message: schedule.errorMessage || '执行失败，请查看发布日志后重试',
      }
    case 'EXPIRED':
      return {
        type: 'warning' as const,
        message: schedule.errorMessage || '已错过计划时间，请重新排期',
      }
    case 'INTERRUPTED':
      return {
        type: 'warning' as const,
        message: schedule.errorMessage || '发布已中断，请先到平台核实结果，避免重复发送',
      }
    case 'DRAFT_CREATED':
      return { type: 'success' as const, message: '已保存到平台草稿箱' }
    case 'PUBLISH_SUBMITTED':
      return { type: 'info' as const, message: '已提交平台，等待平台确认发布结果' }
    case 'WAITING_MANUAL_CONFIRM':
      return { type: 'info' as const, message: '发布资料已准备好，请完成发布后人工确认' }
    case 'PUBLISHED':
    case 'MANUAL_PUBLISHED':
      return { type: 'success' as const, message: '发布已完成' }
    case 'CANCELLED':
      return { type: 'success' as const, message: '排期已取消' }
    default:
      return { type: 'info' as const, message: '操作已记录，请查看当前任务状态' }
  }
}
