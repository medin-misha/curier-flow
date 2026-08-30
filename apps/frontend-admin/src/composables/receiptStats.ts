import type { Receipt, ReceiptYearSummary } from '../types/receipt'

function moneyToCents(value: string) {
  const match = /^(\d+)(?:\.(\d{1,2}))?$/.exec(value)
  if (!match) throw new Error(`Invalid receipt amount: ${value}`)
  return BigInt(match[1]) * 100n + BigInt((match[2] ?? '').padEnd(2, '0'))
}

function centsToMoney(value: bigint) {
  return `${value / 100n}.${String(value % 100n).padStart(2, '0')}`
}

export function aggregateReceiptYears(receipts: Receipt[]): ReceiptYearSummary[] {
  const totals = new Map<number, { count: number; amount: bigint }>()
  for (const receipt of receipts) {
    const year = Number(receipt.date.slice(0, 4))
    const current = totals.get(year) ?? { count: 0, amount: 0n }
    current.count += 1
    current.amount += moneyToCents(receipt.amount)
    totals.set(year, current)
  }
  return [...totals.entries()]
    .sort(([left], [right]) => right - left)
    .map(([year, total]) => ({
      year,
      count: total.count,
      amount: centsToMoney(total.amount),
    }))
}
