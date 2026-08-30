import type {
  Receipt,
  ReceiptCreateInput,
  ReceiptPatchInput,
} from '../types/receipt'
import { ApiError, apiErrorMessage, apiRequest, jsonBody } from './client'

interface ReceiptResponse {
  id: string
  file_id: string
  amount: string
  date: string
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

export async function listReceipts(params: { cursor: string | null; limit: number }) {
  const query = new URLSearchParams({ limit: String(params.limit) })
  if (params.cursor) query.set('cursor', params.cursor)
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
      { file_id: input.fileId, amount: input.amount, date: input.date },
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
    }),
  })
  return mapReceipt(response)
}

export function deleteReceipt(receiptId: string) {
  return apiRequest<void>(`/receipts/${receiptId}`, { method: 'DELETE' })
}

export function receiptErrorMessage(error: unknown, fallback: string) {
  if (error instanceof ApiError) {
    if (error.problem?.reason === 'receipt-file-in-use') {
      return 'Этот файл уже связан с другим чеком.'
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
    if (error.status === 404) return 'Чек или связанный файл больше не существует.'
  }
  return apiErrorMessage(error, fallback)
}
