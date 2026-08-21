import { describe, expect, it } from 'vitest'
import { emptyFiles, emptyForm } from './form.types'
import { reviewRows } from './reviewRows'

function scan(name: string): File {
  return new File(['x'], name, { type: 'image/png' })
}

const filled = {
  ...emptyForm,
  fullName: 'Ivan Ivanov',
  birthDate: '1998-03-10',
  city: 'Praha',
  address: 'Malá Michnovka 1095/20',
  phone: '777123456',
  email: 'ivan@email.com',
  messenger: 'Telegram' as const,
  messengerContact: '@ivan',
  bankAccount: 'CZ00 1234 5678',
  citizenship: 'Украина',
}

describe('reviewRows', () => {
  it('отдаёт десять строк в порядке шагов, каждая со своим шагом правки', () => {
    expect(reviewRows(filled, emptyFiles).map((row) => [row.label, row.step])).toEqual([
      ['Имя', 1],
      ['Рождение', 1],
      ['Город', 1],
      ['Адрес', 1],
      ['Телефон', 2],
      ['Почта', 2],
      ['Telegram', 2],
      ['Счёт', 3],
      ['Гражданство', 3],
      ['Сканы', 3],
    ])
  })

  it('форматирует телефон с префиксом', () => {
    const phone = reviewRows(filled, emptyFiles).find((row) => row.label === 'Телефон')
    expect(phone?.value).toBe('+420 777123456')
  })

  it('вычищает разделители из телефона перед выводом', () => {
    const withSeparators = { ...filled, phone: '+420 777 123 456' }
    const phone = reviewRows(withSeparators, emptyFiles).find((row) => row.label === 'Телефон')

    expect(phone?.value).toBe('+420 420777123456')
  })

  it('подписывает строку контакта выбранным мессенджером', () => {
    const contact = reviewRows(filled, emptyFiles).find((row) => row.label === 'Telegram')
    expect(contact?.value).toBe('@ivan')
    expect(contact?.step).toBe(2)
  })

  it('различает заполненное значение и пустое', () => {
    const populated = reviewRows(filled, emptyFiles).find((row) => row.label === 'Имя')
    expect(populated?.value).toBe('Ivan Ivanov')
    expect(populated?.filled).toBe(true)

    const empty = reviewRows(emptyForm, emptyFiles).find((row) => row.label === 'Имя')
    expect(empty?.value).toBe('—')
    expect(empty?.filled).toBe(false)
  })

  it('считает загруженные сканы', () => {
    const of = (files: Parameters<typeof reviewRows>[1]) =>
      reviewRows(filled, files).find((row) => row.label === 'Сканы')?.value

    expect(of(emptyFiles)).toBe('—')
    expect(of({ passport: scan('p.png'), visa: null })).toBe('1 из 2')
    expect(of({ passport: scan('p.png'), visa: scan('v.png') })).toBe('паспорт + виза')
  })
})
