import type { Messenger } from './form.types'
import { MIN_AGE, PHONE_DIGITS, ageOn, digitsOnly } from './validation'

/** Подсказка под датой рождения. */
export function ageHint(birthDate: string, today: Date): string {
  const age = ageOn(birthDate, today)
  if (age === null) return 'Работаем с курьерами от 18 лет'
  if (age < MIN_AGE) return 'Нужно 18 лет и больше'

  return `${age} лет — подходит`
}

/** Подсказка под телефоном. */
export function phoneHint(phone: string): string {
  return digitsOnly(phone).length === PHONE_DIGITS
    ? 'Номер выглядит верно'
    : '9 цифр, например 777 123 456'
}

/** Подсказка под контактом в мессенджере. */
export function messengerHint(messenger: Messenger): string {
  return messenger === 'Telegram'
    ? 'Ник в Telegram — с собакой в начале'
    : 'Номер, привязанный к WhatsApp'
}

/** Плейсхолдер поля контакта. */
export function messengerPlaceholder(messenger: Messenger): string {
  return messenger === 'Telegram' ? '@username' : '+420 777 123 456'
}
