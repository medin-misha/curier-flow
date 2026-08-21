import { describe, expect, it } from 'vitest'
import { ageHint, messengerHint, messengerPlaceholder, phoneHint } from './hints'

const TODAY = new Date(2026, 7, 14)

describe('ageHint', () => {
  it('без даты зовёт на общее правило', () => {
    expect(ageHint('', TODAY)).toBe('Работаем с курьерами от 18 лет')
  })

  it('до 18 лет говорит о нехватке', () => {
    expect(ageHint('2010-01-01', TODAY)).toBe('Нужно 18 лет и больше')
  })

  it('с 18 лет подтверждает', () => {
    expect(ageHint('1998-03-10', TODAY)).toBe('28 лет — подходит')
  })

  it('на ровно 18 годах уже подходит', () => {
    expect(ageHint('2008-08-14', TODAY)).toBe('18 лет — подходит')
    expect(ageHint('2008-08-15', TODAY)).toBe('Нужно 18 лет и больше')
  })
})

describe('phoneHint', () => {
  it('подтверждает полный номер', () => {
    expect(phoneHint('777123456')).toBe('Номер выглядит верно')
  })

  it('подсказывает формат неполному', () => {
    expect(phoneHint('777')).toBe('9 цифр, например 777 123 456')
    expect(phoneHint('7771234567')).toBe('9 цифр, например 777 123 456')
  })
})

describe('подсказки мессенджера', () => {
  it('различает Telegram и WhatsApp', () => {
    expect(messengerHint('Telegram')).toBe('Ник в Telegram — с собакой в начале')
    expect(messengerHint('WhatsApp')).toBe('Номер, привязанный к WhatsApp')
    expect(messengerPlaceholder('Telegram')).toBe('@username')
    expect(messengerPlaceholder('WhatsApp')).toBe('+420 777 123 456')
  })
})
