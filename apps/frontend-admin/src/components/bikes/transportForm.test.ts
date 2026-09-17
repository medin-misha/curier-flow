import { describe, expect, it } from 'vitest'
import { validateTransportInput, type TransportFormInput } from './transportForm'

const validInput: TransportFormInput = {
  type: 'e-bike',
  model: 'City Runner',
  serialNumber: 'BIKE-001',
  ordinalNumber: '',
  color: 'Чёрный',
  depositRequired: false,
  depositAmount: '',
  rentalPrice: '1250.00',
  comment: '',
  debtAmount: '0.00',
}

describe('Порядковый номер транспорта', () => {
  it.each(['0', '-1', '1.5', '1,5', 'abc', '1e2', '2147483648'])('отклоняет %s', (ordinalNumber) => {
    const result = validateTransportInput({ ...validInput, ordinalNumber })
    expect(result.value).toBeNull()
    expect(result.errors.ordinalNumber).toContain('целое число от 1 до 2147483647')
  })

  it.each([
    ['', null],
    ['   ', null],
    ['1', 1],
    [' 42 ', 42],
    ['2147483647', 2147483647],
  ] as const)('преобразует %s в %s', (ordinalNumber, expected) => {
    const result = validateTransportInput({ ...validInput, ordinalNumber })
    expect(result.errors).toEqual({})
    expect(result.value?.ordinalNumber).toBe(expected)
  })
})
