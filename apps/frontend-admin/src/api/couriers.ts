import type {
  Courier,
  CourierBulkDeleteResult,
  CourierBulkStatusInput,
  CourierBulkStatusResult,
  CourierCreateInput,
  CourierDocument,
  CourierDocumentCreateInput,
  CourierPlatform,
  CourierUpdateInput,
  DeliveryPlatform,
  DocumentPurpose,
  DocumentReviewStatus,
  DocumentType,
  FileStatus,
  PlatformStatus,
} from '../types/courier'
import { ApiError, apiErrorMessage, apiRequest, jsonBody } from './client'

interface FileResponse {
  id: string
  original_name: string
  content_type: string
  size: number
  status: FileStatus
  etag: string | null
  owner_id: string | null
  created_at: string
}

interface PlatformAccountResponse {
  id: string
  courier_id: string
  platform: DeliveryPlatform
  status: PlatformStatus
  created_at: string
  updated_at: string
}

interface CourierDocumentResponse {
  id: string
  courier_id: string
  file_id: string
  type: DocumentType
  purpose: DocumentPurpose
  legal_hold_until: string | null
  file: FileResponse
  created_at: string
  updated_at: string
}

export interface CourierResponse {
  id: string
  full_name: string
  email: string
  phone: string
  date_of_birth: string
  city: string | null
  address: string | null
  citizenship: string | null
  bank_account: string | null
  contact_platform: string | null
  contact: string | null
  source: string | null
  consent_to_processing: boolean
  consent_at: string | null
  platform_accounts: PlatformAccountResponse[]
  documents: CourierDocumentResponse[]
  created_at: string
  updated_at: string
}

interface CourierPageResponse {
  items: CourierResponse[]
  next_cursor: string | null
}

const platformLabels: Record<DeliveryPlatform, string> = {
  bolt_food: 'Bolt Food',
  foodora: 'Foodora',
  wolt: 'Wolt',
}

const documentTypeLabels: Record<DocumentType, string> = {
  passport: 'Паспорт',
  identity_card: 'Удостоверение личности',
  residence_permit: 'Вид на жительство',
  work_permit: 'Разрешение на работу',
  driving_license: 'Водительское удостоверение',
  other: 'Другой документ',
}

const documentPurposeLabels: Record<DocumentPurpose, string> = {
  platform_onboarding: 'Регистрация на платформе',
  employment_compliance: 'Трудовые требования',
  other: 'Другая цель',
}

function mapPlatformAccount(account: PlatformAccountResponse): CourierPlatform {
  return {
    id: account.id,
    platform: account.platform,
    name: platformLabels[account.platform],
    status: account.status,
  }
}

function documentReviewStatus(status: FileStatus): DocumentReviewStatus {
  if (status === 'ready') return 'ready'
  if (status === 'pending') return 'processing'
  return 'rejected'
}

function documentSummary(documents: CourierDocumentResponse[]) {
  if (!documents.length) return 'Нет документов'
  const pending = documents.filter((document) => document.file.status === 'pending').length
  if (pending) return `${pending} на проверке`
  return 'Проверены'
}

function mapCourierDocument(document: CourierDocumentResponse): CourierDocument {
  return {
    id: document.id,
    type: document.type,
    typeLabel: documentTypeLabels[document.type],
    purpose: document.purpose,
    purposeLabel: documentPurposeLabels[document.purpose],
    reviewStatus: documentReviewStatus(document.file.status),
    file: {
      id: document.file.id,
      originalName: document.file.original_name,
      contentType: document.file.content_type,
      size: document.file.size,
      status: document.file.status,
      ownerId: document.file.owner_id,
      createdAt: document.file.created_at,
    },
    createdAt: document.created_at,
    updatedAt: document.updated_at,
  }
}

export function mapCourier(response: CourierResponse): Courier {
  return {
    id: response.id,
    fullName: response.full_name,
    email: response.email,
    phone: response.phone,
    birthDate: response.date_of_birth,
    city: response.city,
    address: response.address,
    citizenship: response.citizenship,
    bank: response.bank_account,
    contactPlatform: response.contact_platform,
    contact: response.contact,
    source: response.source,
    consent: response.consent_to_processing,
    consentAt: response.consent_at,
    platforms: response.platform_accounts.map(mapPlatformAccount),
    documents: response.documents.length,
    documentFiles: response.documents.map(mapCourierDocument),
    documentStatus: documentSummary(response.documents),
    createdAt: response.created_at,
    updatedAt: response.updated_at,
    updated: new Intl.DateTimeFormat('ru-RU').format(new Date(response.updated_at)),
  }
}

function searchParams(query: string): Record<string, string> {
  const normalized = query.trim()
  if (!normalized) return {}
  if (normalized.includes('@')) return { email: normalized }
  if (/^[+\d\s().-]+$/.test(normalized)) return { phone: normalized }
  return { full_name: normalized }
}

export async function listCouriers(options: {
  cursor?: string | null
  limit: number
  query: string
  status?: PlatformStatus | ''
}) {
  const params = new URLSearchParams({
    limit: String(options.limit),
    ...searchParams(options.query),
  })
  if (options.status) params.set('status', options.status)
  if (options.cursor) params.set('cursor', options.cursor)

  const response = await apiRequest<CourierPageResponse>(`/courier?${params.toString()}`)
  return {
    items: response.items.map(mapCourier),
    nextCursor: response.next_cursor,
  }
}

export async function getCourier(courierId: string) {
  return mapCourier(await apiRequest<CourierResponse>(`/courier/${courierId}`))
}

function scalarPayload(values: CourierUpdateInput) {
  return {
    full_name: values.fullName.trim(),
    email: values.email.trim(),
    phone: values.phone.trim(),
    date_of_birth: values.birthDate,
    city: values.city.trim() || null,
    address: values.address.trim() || null,
    citizenship: values.citizenship.trim() || null,
    bank_account: values.bankAccount.trim() || null,
    contact_platform: values.contactPlatform || null,
    contact: values.contact.trim() || null,
    source: values.source || null,
    consent_to_processing: values.consent,
  }
}

export async function createCourier(input: CourierCreateInput) {
  const data = new FormData()
  data.append(
    'payload',
    JSON.stringify({
      ...scalarPayload(input.courier),
      platform_accounts: [{ platform: input.platform }],
      documents: input.document
        ? [{ type: input.document.type, purpose: input.document.purpose }]
        : [],
    }),
  )
  if (input.document) data.append('files', input.document.file)

  return mapCourier(
    await apiRequest<CourierResponse>('/courier', {
      method: 'POST',
      body: data,
    }),
  )
}

export async function updateCourier(courierId: string, input: CourierUpdateInput) {
  return mapCourier(
    await apiRequest<CourierResponse>(`/courier/${courierId}`, {
      method: 'PATCH',
      ...jsonBody(scalarPayload(input)),
    }),
  )
}

export async function addCourierDocument(
  courierId: string,
  input: CourierDocumentCreateInput,
) {
  const data = new FormData()
  data.append('payload', JSON.stringify({ type: input.type, purpose: input.purpose }))
  data.append('file', input.file)

  return mapCourierDocument(
    await apiRequest<CourierDocumentResponse>(`/courier/${courierId}/documents`, {
      method: 'POST',
      body: data,
    }),
  )
}

export async function updateCourierPlatformStatus(
  courierId: string,
  accountId: string,
  status: PlatformStatus,
) {
  const account = await apiRequest<PlatformAccountResponse>(
    `/courier/${courierId}/platform-accounts/${accountId}`,
    {
      method: 'PATCH',
      ...jsonBody({ status }),
    },
  )
  return mapPlatformAccount(account)
}

export function deleteCourier(courierId: string) {
  return apiRequest<void>(`/courier/${courierId}`, {
    method: 'DELETE',
  })
}

function bulkBody(payload: unknown, idempotencyKey: string) {
  const body = jsonBody(payload)
  const headers = new Headers(body.headers)
  headers.set('Idempotency-Key', idempotencyKey)
  return { ...body, headers }
}

export async function bulkDeleteCouriers(
  courierIds: string[],
  idempotencyKey: string,
): Promise<CourierBulkDeleteResult> {
  const response = await apiRequest<{ deleted_count: number }>('/courier/bulk-delete', {
    method: 'POST',
    ...bulkBody({ courier_ids: courierIds }, idempotencyKey),
  })
  return { deletedCount: response.deleted_count }
}

export async function bulkUpdateCourierStatus(
  courierIds: string[],
  input: CourierBulkStatusInput,
  idempotencyKey: string,
): Promise<CourierBulkStatusResult> {
  const response = await apiRequest<{ updated_count: number; unchanged_count: number }>(
    '/courier/bulk-status',
    {
      method: 'PATCH',
      ...bulkBody(
        { courier_ids: courierIds, platform: input.platform, status: input.status },
        idempotencyKey,
      ),
    },
  )
  return { updatedCount: response.updated_count, unchangedCount: response.unchanged_count }
}

export function courierBulkErrorMessage(error: unknown, couriers: Courier[]) {
  const fallback = 'Не удалось получить результат операции. Повторите запрос с теми же параметрами.'
  if (!(error instanceof ApiError)) return fallback

  const problem = error.problem
  const ids = problem?.courier_ids ?? (problem?.courier_id ? [problem.courier_id] : [])
  const names = ids.map((id) => couriers.find((courier) => courier.id === id)?.fullName ?? id)
  const affected = names.length ? ` Курьеры: ${names.join(', ')}.` : ''

  if (error.status === 404) {
    return `Некоторые курьеры больше не существуют. Обновите реестр и выбор.${affected} Операция отменена для всей выборки.`
  }
  if (problem?.reason === 'platform-account-missing') {
    return `У некоторых курьеров нет регистрации на выбранной платформе.${affected} Статусы всей выборки остались прежними.`
  }
  if (problem?.reason === 'signed-contract-protects-rental') {
    return `Удаление запрещено: в истории аренды есть подписанный договор.${affected} Ни один курьер не удалён.`
  }
  if (problem?.reason === 'payload-mismatch') {
    return 'Этот ключ уже использован с другими параметрами. Закройте форму и сформируйте операцию заново.'
  }
  if (problem?.reason === 'in-flight' || problem?.reason === 'in-progress') {
    return 'Операция ещё выполняется. Повторите запрос через несколько секунд.'
  }
  if (error.status === 401 || error.status === 403) {
    return 'Для этой операции требуется действующая сессия администратора.'
  }
  if (error.status === 422) {
    return 'Выберите от 1 до 100 разных курьеров и проверьте платформу и статус.'
  }
  return apiErrorMessage(error, fallback)
}
