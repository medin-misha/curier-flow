import { describe, expect, it } from 'vitest'
import { formatReceiptDate, todayInPrague, validateReceiptDate } from './receiptDate'

describe('receipt date', () => {
  it('вычисляет текущую календарную дату в Europe/Prague', () => {
    expect(todayInPrague(new Date('2026-08-30T22:30:00Z'))).toBe('2026-08-31')
  })

  it('проверяет и форматирует date-only значение без часового пояса', () => {
    expect(validateReceiptDate('')).toBe('Укажите дату чека.')
    expect(validateReceiptDate('2026-08-30')).toBe('')
    expect(formatReceiptDate('2026-08-30')).toBe('30.08.2026')
  })
})
