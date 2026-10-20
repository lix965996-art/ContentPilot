import type { GenerationTask, Variant } from '@/types/business'

export interface GenerationTicket {
  articleId: number
  active: () => boolean
}

export function useGenerationPolling(options: {
  articleId: () => number | undefined
  fetchTask: (id: string) => Promise<GenerationTask>
  fetchVariants: (articleId: number) => Promise<Variant[]>
  onTask: (task: GenerationTask) => void
  onComplete: (task: GenerationTask, variants: Variant[]) => void
  intervalMs?: number
  maxAttempts?: number
}) {
  let sequence = 0
  let wake: (() => void) | undefined
  let timer: ReturnType<typeof setTimeout> | undefined
  function cancel() {
    sequence += 1
    if (timer) clearTimeout(timer)
    timer = undefined
    wake?.()
    wake = undefined
  }
  function begin(articleId: number): GenerationTicket {
    cancel()
    const request = sequence
    return { articleId, active: () => request === sequence && articleId === options.articleId() }
  }
  async function poll(taskId: string, ticket: GenerationTicket) {
    for (
      let attempt = 0;
      attempt < (options.maxAttempts ?? 1200) && ticket.active();
      attempt += 1
    ) {
      const task = await options.fetchTask(taskId)
      if (!ticket.active()) return
      options.onTask(task)
      if (['SUCCESS', 'PARTIAL_SUCCESS', 'FAILED'].includes(task.status)) {
        const variants = await options.fetchVariants(ticket.articleId)
        if (!ticket.active()) return
        options.onComplete(task, variants)
        return task
      }
      await new Promise<void>((resolve) => {
        wake = resolve
        timer = setTimeout(() => {
          timer = undefined
          wake = undefined
          resolve()
        }, options.intervalMs ?? 400)
      })
    }
    if (ticket.active()) throw new Error('生成任务轮询超时')
  }
  return { begin, poll, cancel }
}
