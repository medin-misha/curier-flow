export type Messenger = 'WhatsApp' | 'Telegram'

export type StepNumber = 1 | 2 | 3 | 4

export interface ApplicationForm {
  fullName: string
  /** ISO-дата `YYYY-MM-DD` из `<input type="date">`. */
  birthDate: string
  city: string
  address: string
  /** Только цифры, без префикса +420, максимум 9 символов. */
  phone: string
  email: string
  messenger: Messenger
  messengerContact: string
  bankAccount: string
  citizenship: string
  consent: boolean
}

export interface ApplicationFiles {
  passport: File | null
  visa: File | null
}

export const emptyForm: ApplicationForm = {
  fullName: '',
  birthDate: '',
  city: '',
  address: '',
  phone: '',
  email: '',
  messenger: 'WhatsApp',
  messengerContact: '',
  bankAccount: '',
  citizenship: '',
  consent: false,
}

export const emptyFiles: ApplicationFiles = { passport: null, visa: null }

export const STEP_LABELS = ['Личные данные', 'Контакты', 'Документы', 'Отправка'] as const

export const LAST_STEP: StepNumber = 4
