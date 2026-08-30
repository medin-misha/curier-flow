const docxContentType =
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
const maxFileSize = 25 * 1024 * 1024

export function normalizeTemplateName(value: string) {
  return value.trim()
}

export function validateTemplateName(value: string) {
  const normalized = normalizeTemplateName(value)
  if (!normalized) return 'Введите название шаблона.'
  if (normalized.length > 255) return 'Название должно быть не длиннее 255 символов.'
  return ''
}

export function validateTemplateFile(file: File | null) {
  if (!file) return 'Выберите DOCX-файл.'
  if (
    file.type.toLowerCase() !== docxContentType ||
    !file.name.toLowerCase().endsWith('.docx') ||
    file.size <= 0 ||
    file.size > maxFileSize
  ) {
    return 'Выберите DOCX-файл размером до 25 МБ.'
  }
  return ''
}
