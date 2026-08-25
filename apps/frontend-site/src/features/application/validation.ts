import type { ApplicationFiles, ApplicationForm, StepNumber } from './form.types'

export const MIN_AGE = 18
export const MAX_AGE = 75
export const PHONE_DIGITS = 9
export const MIN_BANK_ACCOUNT_DIGITS = 8

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

function validateIdentity(form: ApplicationForm, today: Date): string {
  const fullName = form.fullName.trim()
  if (!fullName) return 'Впиши имя и фамилию.'
  if (fullName.split(/\s+/).length < 2) return 'Нужно имя и фамилия — два слова.'
  if (!form.birthDate) return 'Укажи дату рождения.'

  const age = ageOn(form.birthDate, today)
  if (age === null || age < MIN_AGE) return 'Работать курьером можно с 18 лет.'
  if (age > MAX_AGE) return 'Проверь дату рождения.'

  if (!form.city.trim()) return 'Выбери или впиши город.'
  if (!form.address.trim()) return 'Впиши адрес проживания.'

  return ''
}

function validateContacts(form: ApplicationForm): string {
  const phone = digitsOnly(form.phone)
  if (!phone) return 'Впиши чешский номер телефона.'
  if (phone.length !== PHONE_DIGITS) return 'Чешский номер — 9 цифр после +420.'
  if (!EMAIL.test(form.email.trim())) return 'Проверь почту.'
  if (!form.messengerContact.trim()) return `Оставь контакт в ${form.messenger}.`

  return ''
}

function validateDocuments(form: ApplicationForm, files: ApplicationFiles): string {
  if (digitsOnly(form.bankAccount).length < MIN_BANK_ACCOUNT_DIGITS) {
    return 'Впиши счёт в чешском банке.'
  }
  if (!form.citizenship) return 'Выбери гражданство.'
  if (!files.passport) return 'Загрузи скан паспорта.'
  if (!files.visa) return 'Загрузи скан визы.'

  return ''
}

/** Текст ошибки шага. Пустая строка означает, что шаг заполнен. */
export function validateStep(
  step: StepNumber,
  form: ApplicationForm,
  files: ApplicationFiles,
  today: Date,
): string {
  if (step === 1) return validateIdentity(form, today)
  if (step === 2) return validateContacts(form)
  if (step === 3) return validateDocuments(form, files)

  return form.consent ? '' : 'Нужно согласие на обработку данных.'
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
): StepNumber | null {
  const steps: StepNumber[] = [1, 2, 3]

  for (const step of steps) {
    if (validateStep(step, form, files, today)) return step
  }

  return null
}
