import { describe, expect, it } from 'vitest'
import type { Receipt } from '../types/receipt'
import { aggregateReceiptYears } from './receiptStats'

function receipt(amount: string, date: string, createdAt: string): Receipt {
  return {
    id: crypto.randomUUID(),
    fileId: crypto.randomUUID(),
    amount,
    date,
    tagId: null,
    createdAt,
    updatedAt: createdAt,
  }
}

describe('aggregateReceiptYears', () => {
  it('суммирует деньги точно и группирует по календарной дате чека', () => {
    expect(
      aggregateReceiptYears([
        receipt('9999999999.99', '2026-08-30', '2026-08-30T10:00:00Z'),
        receipt('0.01', '2026-01-01', '2026-01-01T00:00:00Z'),
        receipt('25.50', '2025-12-31', '2025-12-31T23:30:00Z'),
        receipt('10.00', '2025-06-15', '2026-06-15T10:00:00Z'),
      ]),
    ).toEqual([
      {
        year: 2026,
        amount: '10000000000.00',
        count: 2,
        months: [
          { month: 1, amount: '0.01', count: 1 },
          { month: 8, amount: '9999999999.99', count: 1 },
        ],
        tags: [{ tagId: null, name: 'Без тега', amount: '10000000000.00', count: 2 }],
      },
      {
        year: 2025,
        amount: '35.50',
        count: 2,
        months: [
          { month: 6, amount: '10.00', count: 1 },
          { month: 12, amount: '25.50', count: 1 },
        ],
        tags: [{ tagId: null, name: 'Без тега', amount: '35.50', count: 2 }],
      },
    ])
  })

  it('объединяет чеки одного месяца', () => {
    const [summary] = aggregateReceiptYears([
      receipt('1.10', '2026-03-01', '2026-03-01T10:00:00Z'),
      receipt('2.20', '2026-03-31', '2026-03-31T10:00:00Z'),
    ])

    expect(summary?.months).toEqual([{ month: 3, amount: '3.30', count: 2 }])
  })
})
