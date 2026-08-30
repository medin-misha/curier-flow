const receiptDatePattern = /^\d{4}-\d{2}-\d{2}$/

export function todayInPrague(now = new Date()) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Europe/Prague',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(now)
  const value = Object.fromEntries(parts.map((part) => [part.type, part.value]))
  return `${value.year}-${value.month}-${value.day}`
}

export function validateReceiptDate(value: string) {
  return receiptDatePattern.test(value) ? '' : 'Укажите дату чека.'
}

export function formatReceiptDate(value: string) {
  const [year, month, day] = value.split('-')
  return `${day}.${month}.${year}`
}
