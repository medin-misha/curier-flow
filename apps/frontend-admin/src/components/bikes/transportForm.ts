import type { TransportComponentInput, TransportInput } from '../../types/transport'

const positiveMoney = /^\d{1,10}(?:[.,]\d{1,2})?$/
const nonNegativeMoney = /^\d{1,10}(?:[.,]\d{1,2})?$/

export function normalizeMoney(value: string) {
  return value.trim().replace(',', '.')
}

export function validateTransportInput(input: TransportInput) {
  const errors: Record<string, string> = {}
  if (!input.type.trim() || input.type.trim().length > 64) errors.type = 'Укажите тип до 64 символов.'
  if (!input.model.trim() || input.model.trim().length > 128) errors.model = 'Укажите модель до 128 символов.'
  if (!input.serialNumber.trim() || input.serialNumber.trim().length > 64) errors.serialNumber = 'Укажите серийный номер до 64 символов.'
  if (!input.color.trim() || input.color.trim().length > 64) errors.color = 'Укажите цвет до 64 символов.'
  if (!positiveMoney.test(input.rentalPrice.trim())) errors.rentalPrice = 'Введите положительную сумму с точностью до 2 знаков.'
  if (Number(normalizeMoney(input.rentalPrice)) <= 0) errors.rentalPrice = 'Ставка должна быть больше нуля.'
  if (!nonNegativeMoney.test(input.debtAmount.trim())) {
    errors.debtAmount = 'Введите задолженность с точностью до 2 знаков.'
  }
  if (input.comment.trim().length > 2000) errors.comment = 'Комментарий не должен превышать 2000 символов.'
  if (input.depositRequired) {
    if (!positiveMoney.test(input.depositAmount.trim()) || Number(normalizeMoney(input.depositAmount)) <= 0) {
      errors.depositAmount = 'Введите положительную сумму залога.'
    }
  }
  return {
    errors,
    value: Object.keys(errors).length
      ? null
      : {
          ...input,
          type: input.type.trim().toLowerCase(),
          model: input.model.trim(),
          serialNumber: input.serialNumber.trim().toUpperCase(),
          color: input.color.trim(),
          rentalPrice: normalizeMoney(input.rentalPrice),
          debtAmount: normalizeMoney(input.debtAmount),
          comment: input.comment.trim(),
          depositAmount: input.depositRequired ? normalizeMoney(input.depositAmount) : '',
        },
  }
}

export function validateComponentInput(input: TransportComponentInput) {
  const errors: Record<string, string> = {}
  if (!input.name.trim() || input.name.trim().length > 128) errors.name = 'Укажите название до 128 символов.'
  if (!nonNegativeMoney.test(input.unitPrice.trim())) errors.unitPrice = 'Введите сумму с точностью до 2 знаков.'
  if (!Number.isInteger(input.quantity) || input.quantity <= 0) errors.quantity = 'Количество должно быть целым и больше нуля.'
  return {
    errors,
    value: Object.keys(errors).length
      ? null
      : { name: input.name.trim(), unitPrice: normalizeMoney(input.unitPrice), quantity: input.quantity },
  }
}
