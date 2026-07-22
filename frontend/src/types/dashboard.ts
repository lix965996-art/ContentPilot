import type { User } from './user'

export interface ServiceStatus {
  api: string
  database: string
  auth: string
  demoMode: boolean
}

export interface DashboardSummary {
  phase: number
  phaseName: string
  user: User
  capabilities: string[]
  serviceStatus: ServiceStatus
  availableModules: string[]
  upcomingModules: string[]
}
