export interface AdminProfileForm {
  username: string
  telegramId: string
}

export interface AdminProfileErrors {
  username: string
  telegramId: string
}

export interface AdminProfileInput {
  username: string
  telegramId: number | null
}

export function validateAdminProfile(form: AdminProfileForm): {
  errors: AdminProfileErrors
  input: AdminProfileInput | null
} {
  const username = form.username.trim().toLowerCase()
  const telegram = form.telegramId.trim()
  const errors: AdminProfileErrors = {
    username: /^[a-z0-9._-]{3,64}$/.test(username)
      ? ''
      : 'От 3 до 64 символов: латиница, цифры, точка, _ или -.',
    telegramId: '',
  }

  let telegramId: number | null = null
  if (telegram) {
    telegramId = Number(telegram)
    if (!/^\d+$/.test(telegram) || !Number.isSafeInteger(telegramId) || telegramId <= 0) {
      errors.telegramId = 'Введите положительное целое число.'
    }
  }

  if (errors.username || errors.telegramId) return { errors, input: null }
  return { errors, input: { username, telegramId } }
}
