export interface LearningPrediction {
  mode: 'MACHINE_LEARNING' | 'STATISTICAL_FALLBACK'
  reason: string | null
  modelId: string | null
  target: string
  expectedInteractions?: number
  explanationTime?: string
  explanations: Array<{ feature: string; contribution: number }>
}

export interface LearningModel {
  modelId: string
  platform: string
  algorithm: string
  target: string
  eligibility: string
  researchOnly: boolean
  activationBlocked: string | null
  test: { count: number; maeLog: number; maeOriginal: number; spearman: number | null }
  improvement: { relativeImprovement: number; difference95CI: [number, number] | null }
  timeValidity: string
  trainRows: number
  validationRows: number
  testRows: number
}

export interface LearningStatus {
  readiness: { accepted: number; accounts: number; status: string; reasons: Record<string, number> }
  items: Array<{
    scheduleId: number
    platform: string
    observedAt: string | null
    ageSeconds: number | null
    status: string
    errorCode: string | null
    likes: number | null
    replies: number | null
    reposts: number | null
    tasks: Array<{
      id: string
      status: string
      dueAt: string
      windowSeconds: number
      errorCode: string | null
    }>
  }>
  activeModels: Record<string, string | null>
  models: LearningModel[]
  exposureAvailable: boolean
}
