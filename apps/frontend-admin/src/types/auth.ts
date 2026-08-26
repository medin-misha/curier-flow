export interface Admin {
  id: string
  username: string
  telegram_id: number | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface LoginCredentials {
  username: string
  password: string
}

export interface AccessToken {
  access_token: string
  token_type: 'bearer'
  expires_in: number
}
