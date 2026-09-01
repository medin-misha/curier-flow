import { getMessages } from '@/i18n/messages'
import type { Locale } from '@/i18n/locales'
import type { Messenger } from './form.types'
import { MIN_AGE, PHONE_DIGITS, ageOn, digitsOnly } from './validation'

/** Подсказка под датой рождения. */
export function ageHint(birthDate: string, today: Date, locale: Locale = 'ru'): string {
  const copy = getMessages(locale).application.hints
  const age = ageOn(birthDate, today)
  if (age === null) return copy.ageEmpty(MIN_AGE)
  if (age < MIN_AGE) return copy.ageTooYoung(MIN_AGE)

  return copy.ageValid(age)
}

/** Подсказка под телефоном. */
export function phoneHint(phone: string, locale: Locale = 'ru'): string {
  const copy = getMessages(locale).application.hints
  return digitsOnly(phone).length === PHONE_DIGITS ? copy.phoneValid : copy.phoneFormat
}

/** Подсказка под контактом в мессенджере. */
export function messengerHint(messenger: Messenger, locale: Locale = 'ru'): string {
  const copy = getMessages(locale).application.hints
  return messenger === 'Telegram' ? copy.telegram : copy.whatsapp
}

/** Плейсхолдер поля контакта. */
export function messengerPlaceholder(messenger: Messenger): string {
  return messenger === 'Telegram' ? '@username' : '+420 777 123 456'
}
