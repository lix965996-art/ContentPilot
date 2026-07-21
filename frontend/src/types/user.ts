export type RoleCode = 'ADMIN' | 'OPERATOR' | 'VIEWER'

export interface Role {
  code: RoleCode
  name: string
}

export interface User {
  id: number
  username: string
  display_name: string
  email: string | null
  avatar_url: string | null
  status: string
  last_login_at: string | null
  roles: Role[]
}

export interface LoginPayload {
  username: string
  password: string
}

export interface AuthData {
  access_token: string
  refresh_token: string
  token_type: 'bearer'
  expires_in: number
  user: User
}
