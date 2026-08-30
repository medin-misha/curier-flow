import type { Admin, AdminCreateInput, AdminUpdateInput } from '../types/admin'
import { ApiError, apiErrorMessage, apiRequest, jsonBody } from './client'

export interface AdminResponse {
  id: string
  username: string
  telegram_id: number | null
  is_active: boolean
  created_at: string
  updated_at: string
}

interface AdminPageResponse {
  items: AdminResponse[]
  next_cursor: string | null
}

export function mapAdmin(response: AdminResponse): Admin {
  return {
    id: response.id,
    username: response.username,
    telegramId: response.telegram_id,
    isActive: response.is_active,
    createdAt: response.created_at,
    updatedAt: response.updated_at,
  }
}

export async function listAdmins({
  cursor,
  limit,
}: {
  cursor?: string | null
  limit: number
}) {
  const params = new URLSearchParams({ limit: String(limit) })
  if (cursor) params.set('cursor', cursor)

  const response = await apiRequest<AdminPageResponse>(
    `/admin/admins?${params.toString()}`,
  )
  return {
    items: response.items.map(mapAdmin),
    nextCursor: response.next_cursor,
  }
}

export async function getAdmin(adminId: string) {
  return mapAdmin(await apiRequest<AdminResponse>(`/admin/admins/${adminId}`))
}

export async function createAdmin(
  input: AdminCreateInput,
  idempotencyKey: string = crypto.randomUUID(),
) {
  const request = jsonBody({
    username: input.username.trim().toLowerCase(),
    password: input.password,
    telegram_id: input.telegramId,
  })
  const headers = new Headers(request.headers)
  headers.set('Idempotency-Key', idempotencyKey)

  return mapAdmin(
    await apiRequest<AdminResponse>('/admin/admins', {
      method: 'POST',
      ...request,
      headers,
    }),
  )
}

export async function updateAdmin(adminId: string, input: AdminUpdateInput) {
  const payload: { username?: string; telegram_id?: number | null } = {}
  if (input.username !== undefined) {
    payload.username = input.username.trim().toLowerCase()
  }
  if (input.telegramId !== undefined) payload.telegram_id = input.telegramId

  return mapAdmin(
    await apiRequest<AdminResponse>(`/admin/admins/${adminId}`, {
      method: 'PATCH',
      ...jsonBody(payload),
    }),
  )
}

export async function activateAdmin(adminId: string) {
  return mapAdmin(
    await apiRequest<AdminResponse>(`/admin/admins/${adminId}/activate`, {
      method: 'POST',
    }),
  )
}

export async function deactivateAdmin(adminId: string) {
  return mapAdmin(
    await apiRequest<AdminResponse>(`/admin/admins/${adminId}/deactivate`, {
      method: 'POST',
    }),
  )
}

export function resetAdminPassword(adminId: string, newPassword: string) {
  return apiRequest<void>(`/admin/admins/${adminId}/reset-password`, {
    method: 'POST',
    ...jsonBody({ new_password: newPassword }),
  })
}

export function adminErrorMessage(error: unknown, fallback: string) {
  if (error instanceof ApiError) {
    if (error.problem?.reason === 'duplicate-admin') {
      return 'Администратор с таким username или Telegram ID уже существует.'
    }
    if (error.problem?.reason === 'self-deactivation') {
      return 'Нельзя деактивировать собственную учётную запись.'
    }
    if (error.problem?.reason === 'last-active-admin') {
      return 'Нельзя деактивировать последнего активного администратора.'
    }
    if (error.problem?.reason === 'payload-mismatch') {
      return 'Запрос создания изменился при повторной отправке. Повторите ещё раз.'
    }
    if (error.problem?.reason === 'in-flight') {
      return 'Создание уже выполняется. Дождитесь завершения запроса.'
    }
    if (error.status === 404) return 'Администратор больше не существует.'
    if (error.status === 422) return 'Проверьте значения полей формы.'
  }
  return apiErrorMessage(error, fallback)
}
