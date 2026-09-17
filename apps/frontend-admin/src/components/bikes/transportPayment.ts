import type { TransportPaymentType } from '../../types/transport'

export const transportPaymentLabels: Record<TransportPaymentType, string> = {
  monthly: 'Месячный',
  weekly: 'Недельный',
  weekly_in_arrears: 'Неделя назад',
}

export function isTransportPaymentType(value: string): value is TransportPaymentType {
  return Object.hasOwn(transportPaymentLabels, value)
}

export function transportPaymentLabel(value: TransportPaymentType | null) {
  return value === null ? 'Не указан' : transportPaymentLabels[value]
}
