export type { Admin } from './admin'

export interface LoginCredentials {
  username: string
  password: string
}

export interface AccessToken {
  access_token: string
  token_type: 'bearer'
  expires_in: number
}
