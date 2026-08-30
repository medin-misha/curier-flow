import type {
  DocumentRenderValues,
  DocumentTemplate,
  DocumentTemplateCreateInput,
  DocumentTemplateFields,
} from '../types/document'
import { ApiError, apiErrorMessage, apiRequest, jsonBody } from './client'

interface DocumentTemplateResponse {
  id: string
  name: string
  file_id: string
  fields: DocumentTemplateFields
  created_at: string
  updated_at: string
}

interface PageResponse<T> {
  items: T[]
  next_cursor: string | null
}

export function mapDocumentTemplate(response: DocumentTemplateResponse): DocumentTemplate {
  return {
    id: response.id,
    name: response.name,
    fileId: response.file_id,
    fields: response.fields,
    createdAt: response.created_at,
    updatedAt: response.updated_at,
  }
}

export async function listDocumentTemplates(params: { cursor: string | null; limit: number }) {
  const query = new URLSearchParams({ limit: String(params.limit) })
  if (params.cursor) query.set('cursor', params.cursor)
  const response = await apiRequest<PageResponse<DocumentTemplateResponse>>(
    `/document-templates?${query}`,
  )
  return {
    items: response.items.map(mapDocumentTemplate),
    nextCursor: response.next_cursor,
  }
}

export async function getDocumentTemplate(templateId: string) {
  return mapDocumentTemplate(
    await apiRequest<DocumentTemplateResponse>(`/document-templates/${templateId}`),
  )
}

export async function createDocumentTemplate(input: DocumentTemplateCreateInput) {
  const response = await apiRequest<DocumentTemplateResponse>('/document-templates', {
    method: 'POST',
    ...jsonBody({ name: input.name, file_id: input.fileId }),
  })
  return mapDocumentTemplate(response)
}

export function renderDocumentTemplate(templateId: string, values: DocumentRenderValues) {
  return apiRequest<Blob>(`/document-templates/${templateId}/render`, {
    method: 'POST',
    ...jsonBody({ values }),
    responseType: 'blob',
  })
}

export function deleteDocumentTemplate(templateId: string) {
  return apiRequest<void>(`/document-templates/${templateId}`, { method: 'DELETE' })
}

function invalidDocxTemplateMessage(detail?: string) {
  const malformed = detail?.match(/^Malformed placeholder: (.+)$/)
  if (malformed) {
    return `Некорректное поле ${malformed[1]}. Используйте формат {courier.full_name}: только строчные латинские буквы, цифры и _.`
  }
  if (detail === 'DOCX template contains no placeholders') {
    return 'Поля не найдены. Добавьте хотя бы одно поле в формате {courier.full_name}.'
  }
  const fieldLimit = detail?.match(/^DOCX template contains (\d+) fields; limit is (\d+)$/)
  if (fieldLimit) {
    return `В DOCX найдено ${fieldLimit[1]} полей, допустимо не больше ${fieldLimit[2]}.`
  }
  if (
    detail === 'File is not a valid DOCX archive' ||
    detail === 'DOCX package has no main Word document'
  ) {
    return 'Файл не является корректным документом DOCX.'
  }
  if (
    detail === 'Macro-enabled DOCX documents are not supported' ||
    detail === 'Only non-macro DOCX documents are supported'
  ) {
    return 'DOCX с макросами не поддерживается. Сохраните файл как обычный документ .docx.'
  }
  return 'DOCX не прошёл проверку. Используйте обычный .docx и поля вида {courier.full_name}.'
}

export function documentErrorMessage(error: unknown, fallback: string) {
  if (error instanceof ApiError) {
    if (error.problem?.reason === 'invalid-docx-template') {
      return invalidDocxTemplateMessage(error.problem.detail)
    }
    const reasonMessages: Record<string, string> = {
      'template-file-in-use': 'Этот DOCX уже используется другим шаблоном.',
      'file-not-ready': 'Файл ещё не готов. Повторите загрузку.',
      'invalid-template-type': 'Для шаблона нужен DOCX-файл.',
      'invalid-template-name': 'Имя файла должно оканчиваться на .docx.',
      'field-mismatch': 'Набор полей не совпадает со схемой шаблона. Обновите карточку.',
      'invalid-field-values': 'Значения должны быть однострочными и не длиннее 10 000 символов.',
      'broken-template-source': 'Исходный DOCX больше нельзя использовать для генерации.',
      'template-source-missing': 'Исходный DOCX отсутствует в хранилище.',
      'template-source-changed': 'Исходный DOCX изменился после подтверждения.',
    }
    if (error.problem?.reason && reasonMessages[error.problem.reason]) {
      return reasonMessages[error.problem.reason]
    }
    if (error.status === 404) return 'Шаблон или его исходный файл больше не существует.'
  }
  return apiErrorMessage(error, fallback)
}
