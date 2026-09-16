import { CZECH_CITIZENSHIP } from '@/content/application'
import { getMessages } from '@/i18n/messages'
import type { Locale } from '@/i18n/locales'
import type { ApplicationFiles, ApplicationForm, StepNumber } from './form.types'

export const MIN_AGE = 15
export const MAX_AGE = 75
export const PHONE_DIGITS = 9
export const MIN_BANK_ACCOUNT_DIGITS = 8
export const MAX_DOCUMENT_FILE_SIZE = 10 * 1024 * 1024
export const DOCUMENT_FILE_ACCEPT = 'image/png,image/jpeg,image/webp,application/pdf'

const DOCUMENT_CONTENT_TYPES = new Set(['image/png', 'image/jpeg', 'image/webp', 'application/pdf'])

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/
const EMAIL = /^\S+@\S+\.\S+$/

/** Убирает из строки всё, кроме цифр. */
export function digitsOnly(value: string): string {
  return value.replace(/[^0-9]/g, '')
}

/**
 * Полных лет на указанную дату. `null`, если дата пустая или битая.
 *
 * Дата разбирается вручную: `new Date('2000-01-15')` — это полночь UTC,
 * и в зонах западнее Гринвича локальные getMonth/getDate сдвигают
 * результат на сутки.
 */
export function ageOn(birthDate: string, today: Date): number | null {
  const match = ISO_DATE.exec(birthDate)
  if (!match) return null

  const born = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]))
  // Date молча переносит выход за границы месяца: 2024-13-40 стало бы 2025-02-09.
  // Сверяем, что разобранные части уцелели.
  if (born.getFullYear() !== Number(match[1])) return null
  if (born.getMonth() !== Number(match[2]) - 1) return null
  if (born.getDate() !== Number(match[3])) return null

  let age = today.getFullYear() - born.getFullYear()
  const monthDiff = today.getMonth() - born.getMonth()
  if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < born.getDate())) age -= 1

  return age
}

function validateIdentity(form: ApplicationForm, today: Date, locale: Locale): string {
  const copy = getMessages(locale).application.errors
  const fullName = form.fullName.trim()
  if (!fullName) return copy.fullNameRequired
  if (fullName.split(/\s+/).length < 2) return copy.fullNameTwoWords
  if (!form.birthDate) return copy.birthDateRequired

  const age = ageOn(form.birthDate, today)
  if (age === null || age < MIN_AGE) return copy.ageMinimum(MIN_AGE)
  if (age > MAX_AGE) return copy.birthDateInvalid

  if (!form.city.trim()) return copy.cityRequired
  if (!form.address.trim()) return copy.addressRequired

  return ''
}

function validateContacts(form: ApplicationForm, locale: Locale): string {
  const copy = getMessages(locale).application.errors
  const phone = digitsOnly(form.phone)
  if (!phone) return copy.phoneRequired
  if (phone.length !== PHONE_DIGITS) return copy.phoneInvalid
  if (!EMAIL.test(form.email.trim())) return copy.emailInvalid
  if (!form.messengerContact.trim()) return copy.messengerRequired(form.messenger)

  return ''
}

function validateDocuments(
  form: ApplicationForm,
  files: ApplicationFiles,
  locale: Locale,
): string {
  const copy = getMessages(locale).application.errors
  if (digitsOnly(form.bankAccount).length < MIN_BANK_ACCOUNT_DIGITS) {
    return copy.bankRequired
  }
  if (!form.citizenship) return copy.citizenshipRequired

  const isCzechCitizen = form.citizenship === CZECH_CITIZENSHIP
  if (!files.passport) {
    return isCzechCitizen ? copy.identityCardFrontRequired : copy.passportRequired
  }
  if (!files.visa) {
    return isCzechCitizen ? copy.identityCardBackRequired : copy.visaRequired
  }

  const fileError =
    validateDocumentFile(files.passport, locale) || validateDocumentFile(files.visa, locale)
  if (fileError) return fileError

  return ''
}

function validateDocumentFile(file: File, locale: Locale): string {
  const copy = getMessages(locale).application.errors
  if (file.size === 0) return copy.fileEmpty(file.name)
  if (!DOCUMENT_CONTENT_TYPES.has(file.type.toLowerCase())) return copy.fileType(file.name)
  if (file.size > MAX_DOCUMENT_FILE_SIZE) return copy.fileLarge(file.name)
  return ''
}

/** Текст ошибки шага. Пустая строка означает, что шаг заполнен. */
export function validateStep(
  step: StepNumber,
  form: ApplicationForm,
  files: ApplicationFiles,
  today: Date,
  locale: Locale = 'ru',
): string {
  if (step === 1) return validateIdentity(form, today, locale)
  if (step === 2) return validateContacts(form, locale)
  if (step === 3) return validateDocuments(form, files, locale)

  return form.consent ? '' : getMessages(locale).application.errors.consentRequired
}

/**
 * Самый ранний незаполненный шаг из первых трёх.
 *
 * Перед отправкой шаги перепроверяются целиком: пользователь мог вернуться
 * назад и стереть уже введённое.
 */
export function firstInvalidStep(
  form: ApplicationForm,
  files: ApplicationFiles,
  today: Date,
  locale: Locale = 'ru',
): StepNumber | null {
  const steps: StepNumber[] = [1, 2, 3]

  for (const step of steps) {
    if (validateStep(step, form, files, today, locale)) return step
  }

  return null
}
