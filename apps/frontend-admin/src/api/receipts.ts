import type {
  Receipt,
  ReceiptCreateInput,
  ReceiptPatchInput,
  ReceiptTag,
} from '../types/receipt'
import { ApiError, apiErrorMessage, apiRequest, jsonBody } from './client'

interface ReceiptResponse {
  id: string
  file_id: string
  amount: string
  date: string
  tag_id: string | null
  created_at: string
  updated_at: string
}

interface ReceiptTagResponse {
  id: string
  name: string
  created_at: string
  updated_at: string
}

interface PageResponse<T> {
  items: T[]
  next_cursor: string | null
}

export function mapReceipt(response: ReceiptResponse): Receipt {
  return {
    id: response.id,
    fileId: response.file_id,
    amount: response.amount,
    date: response.date,
    tagId: response.tag_id,
    createdAt: response.created_at,
    updatedAt: response.updated_at,
  }
}

function mapReceiptTag(response: ReceiptTagResponse): ReceiptTag {
  return {
    id: response.id,
    name: response.name,
    createdAt: response.created_at,
    updatedAt: response.updated_at,
  }
}

function commandBody(value: unknown, idempotencyKey: string) {
  const request = jsonBody(value)
  const headers = new Headers(request.headers)
  headers.set('Idempotency-Key', idempotencyKey)
  return { ...request, headers }
}

export async function listReceipts(params: {
  cursor: string | null
  limit: number
  tagId?: string | null
}) {
  const query = new URLSearchParams({ limit: String(params.limit) })
  if (params.cursor) query.set('cursor', params.cursor)
  if (params.tagId) query.set('tag_id', params.tagId)
  const response = await apiRequest<PageResponse<ReceiptResponse>>(`/receipts?${query}`)
  return {
    items: response.items.map(mapReceipt),
    nextCursor: response.next_cursor,
  }
}

export async function getReceipt(receiptId: string) {
  return mapReceipt(await apiRequest<ReceiptResponse>(`/receipts/${receiptId}`))
}

export async function createReceipt(input: ReceiptCreateInput, idempotencyKey: string) {
  const response = await apiRequest<ReceiptResponse>('/receipts', {
    method: 'POST',
    ...commandBody(
      {
        file_id: input.fileId,
        amount: input.amount,
        date: input.date,
        tag_id: input.tagId,
      },
      idempotencyKey,
    ),
  })
  return mapReceipt(response)
}

export async function updateReceipt(receiptId: string, input: ReceiptPatchInput) {
  const response = await apiRequest<ReceiptResponse>(`/receipts/${receiptId}`, {
    method: 'PATCH',
    ...jsonBody({
      ...(input.fileId !== undefined ? { file_id: input.fileId } : {}),
      ...(input.amount !== undefined ? { amount: input.amount } : {}),
      ...(input.date !== undefined ? { date: input.date } : {}),
      ...(input.tagId !== undefined ? { tag_id: input.tagId } : {}),
    }),
  })
  return mapReceipt(response)
}

export function deleteReceipt(receiptId: string) {
  return apiRequest<void>(`/receipts/${receiptId}`, { method: 'DELETE' })
}

export async function listReceiptTags(params: { cursor: string | null; limit: number }) {
  const query = new URLSearchParams({ limit: String(params.limit) })
  if (params.cursor) query.set('cursor', params.cursor)
  const response = await apiRequest<PageResponse<ReceiptTagResponse>>(`/receipts/tags?${query}`)
  return {
    items: response.items.map(mapReceiptTag),
    nextCursor: response.next_cursor,
  }
}

export async function createReceiptTag(name: string, idempotencyKey: string) {
  const response = await apiRequest<ReceiptTagResponse>('/receipts/tags', {
    method: 'POST',
    ...commandBody({ name }, idempotencyKey),
  })
  return mapReceiptTag(response)
}

export async function updateReceiptTag(tagId: string, name: string) {
  const response = await apiRequest<ReceiptTagResponse>(`/receipts/tags/${tagId}`, {
    method: 'PATCH',
    ...jsonBody({ name }),
  })
  return mapReceiptTag(response)
}

export function deleteReceiptTag(tagId: string) {
  return apiRequest<void>(`/receipts/tags/${tagId}`, { method: 'DELETE' })
}

export function receiptErrorMessage(error: unknown, fallback: string) {
  if (error instanceof ApiError) {
    if (error.problem?.reason === 'receipt-file-in-use') {
      return 'Этот файл уже связан с другим чеком.'
    }
    if (error.problem?.reason === 'receipt-tag-name-in-use') {
      return 'Тег с таким названием уже существует.'
    }
    if (error.problem?.reason === 'file-not-ready') {
      return 'Файл ещё не готов. Повторите загрузку.'
    }
    if (error.problem?.reason === 'payload-mismatch') {
      return 'Данные изменились после первой попытки. Закройте форму и попробуйте снова.'
    }
    if (error.problem?.reason === 'in-flight') {
      return 'Чек уже создаётся. Повторите попытку через несколько секунд.'
    }
    if (error.status === 404) return 'Чек, тег или связанный файл больше не существует.'
  }
  return apiErrorMessage(error, fallback)
}
