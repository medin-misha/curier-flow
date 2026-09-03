import { CZECH_CITIZENSHIP, getCountryOptions } from '@/content/application'
import { getMessages } from '@/i18n/messages'
import type { Locale } from '@/i18n/locales'
import type { ApplicationFiles, ApplicationForm, StepNumber } from './form.types'
import { digitsOnly } from './validation'

export interface ReviewRow {
  label: string
  /** Готовое к выводу значение; для пустого поля — прочерк. */
  value: string
  /** Шаг, на который ведёт кнопка «Изм.». */
  step: StepNumber
  filled: boolean
}

function row(label: string, value: string, step: StepNumber): ReviewRow {
  const filled = value.length > 0
  return { label, value: filled ? value : '—', step, filled }
}

function scansValue(form: ApplicationForm, files: ApplicationFiles, locale: Locale): string {
  const copy = getMessages(locale).application.review.rows
  if (files.passport && files.visa) {
    return form.citizenship === CZECH_CITIZENSHIP ? copy.identityCardScans : copy.bothScans
  }
  if (files.passport || files.visa) return copy.oneOfTwo
  return ''
}

/** Сводка перед отправкой: что введено и на каком шаге это править. */
export function reviewRows(
  form: ApplicationForm,
  files: ApplicationFiles,
  locale: Locale = 'ru',
): ReviewRow[] {
  const phone = digitsOnly(form.phone)
  const copy = getMessages(locale).application.review.rows
  const citizenship =
    getCountryOptions(locale).find((country) => country.value === form.citizenship)?.label ??
    form.citizenship

  return [
    row(copy.name, form.fullName, 1),
    row(copy.birthDate, form.birthDate, 1),
    row(copy.city, form.city, 1),
    row(copy.address, form.address, 1),
    row(copy.phone, phone ? `+420 ${phone}` : '', 2),
    row(copy.email, form.email, 2),
    row(form.messenger, form.messengerContact, 2),
    row(copy.bankAccount, form.bankAccount, 3),
    row(copy.citizenship, citizenship, 3),
    row(copy.scans, scansValue(form, files, locale), 3),
  ]
}
