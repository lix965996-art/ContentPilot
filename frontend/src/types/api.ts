export interface ApiResponse<T> {
  code: number
  message: string
  data: T
  traceId: string
}

export interface ApiErrorData {
  field?: string
  message?: string
  type?: string
}
