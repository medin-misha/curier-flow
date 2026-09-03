import type {
  Receipt,
  ReceiptMonthSummary,
  ReceiptTag,
  ReceiptYearSummary,
} from '../types/receipt'

function moneyToCents(value: string) {
  const match = /^(\d+)(?:\.(\d{1,2}))?$/.exec(value)
  if (!match) throw new Error(`Invalid receipt amount: ${value}`)
  return BigInt(match[1]) * 100n + BigInt((match[2] ?? '').padEnd(2, '0'))
}

function centsToMoney(value: bigint) {
  return `${value / 100n}.${String(value % 100n).padStart(2, '0')}`
}

export function aggregateReceiptYears(
  receipts: Receipt[],
  tags: ReceiptTag[] = [],
): ReceiptYearSummary[] {
  const totals = new Map<
    number,
    {
      count: number
      amount: bigint
      months: Map<number, { count: number; amount: bigint }>
      tags: Map<string | null, { count: number; amount: bigint }>
    }
  >()
  const tagNames = new Map(tags.map((tag) => [tag.id, tag.name]))
  for (const receipt of receipts) {
    const year = Number(receipt.date.slice(0, 4))
    const month = Number(receipt.date.slice(5, 7))
    const current =
      totals.get(year) ?? { count: 0, amount: 0n, months: new Map(), tags: new Map() }
    const amount = moneyToCents(receipt.amount)
    current.count += 1
    current.amount += amount
    const monthly = current.months.get(month) ?? { count: 0, amount: 0n }
    monthly.count += 1
    monthly.amount += amount
    current.months.set(month, monthly)
    const tag = current.tags.get(receipt.tagId) ?? { count: 0, amount: 0n }
    tag.count += 1
    tag.amount += amount
    current.tags.set(receipt.tagId, tag)
    totals.set(year, current)
  }
  return [...totals.entries()]
    .sort(([left], [right]) => right - left)
    .map(([year, total]) => ({
      year,
      count: total.count,
      amount: centsToMoney(total.amount),
      months: [...total.months.entries()]
        .sort(([left], [right]) => left - right)
        .map(([month, value]): ReceiptMonthSummary => ({
          month,
          count: value.count,
          amount: centsToMoney(value.amount),
        })),
      tags: [...total.tags.entries()]
        .map(([tagId, value]) => ({
          tagId,
          name: tagId ? (tagNames.get(tagId) ?? 'Удалённый тег') : 'Без тега',
          count: value.count,
          amount: centsToMoney(value.amount),
        }))
        .sort((left, right) => right.count - left.count || left.name.localeCompare(right.name, 'ru')),
    }))
}
