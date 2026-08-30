export interface Admin {
  id: string
  username: string
  telegramId: number | null
  isActive: boolean
  createdAt: string
  updatedAt: string
}

export interface AdminCreateInput {
  username: string
  password: string
  telegramId: number | null
}

export interface AdminUpdateInput {
  username?: string
  telegramId?: number | null
}

export interface AdminPasswordResetInput {
  newPassword: string
}
