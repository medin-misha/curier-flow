const positiveMoney = /^\d{1,10}(?:[.,]\d{1,2})?$/
const allowedFileTypes = new Set([
  'application/pdf',
  'image/jpeg',
  'image/png',
  'image/webp',
])
const maxFileSize = 25 * 1024 * 1024

export function normalizeReceiptAmount(value: string) {
  return value.trim().replace(',', '.')
}

export function validateReceiptAmount(value: string) {
  const normalized = normalizeReceiptAmount(value)
  if (!positiveMoney.test(normalized) || Number(normalized) <= 0) {
    return 'Введите положительную сумму до 10 цифр с точностью до 2 знаков.'
  }
  return ''
}

export function validateReceiptFile(file: File | null, required: boolean) {
  if (!file) return required ? 'Выберите файл чека.' : ''
  if (!allowedFileTypes.has(file.type) || file.size <= 0 || file.size > maxFileSize) {
    return 'Выберите PDF, JPG, PNG или WebP размером до 25 МБ.'
  }
  return ''
}
