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

function scansValue(files: ApplicationFiles): string {
  if (files.passport && files.visa) return 'паспорт + виза / ВНЖ'
  if (files.passport || files.visa) return '1 из 2'
  return ''
}

/** Сводка перед отправкой: что введено и на каком шаге это править. */
export function reviewRows(form: ApplicationForm, files: ApplicationFiles): ReviewRow[] {
  const phone = digitsOnly(form.phone)

  return [
    row('Имя', form.fullName, 1),
    row('Рождение', form.birthDate, 1),
    row('Город', form.city, 1),
    row('Адрес', form.address, 1),
    row('Телефон', phone ? `+420 ${phone}` : '', 2),
    row('Почта', form.email, 2),
    row(form.messenger, form.messengerContact, 2),
    row('Счёт', form.bankAccount, 3),
    row('Гражданство', form.citizenship, 3),
    row('Сканы', scansValue(files), 3),
  ]
}
