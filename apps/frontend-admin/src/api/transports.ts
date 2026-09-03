import type {
  ContractFile,
  Transport,
  TransportComponent,
  TransportComponentInput,
  TransportFilters,
  TransportInput,
  TransportListItem,
  TransportRental,
  TransportRentalInput,
} from '../types/transport'
import { ApiError, apiErrorMessage, apiRequest, jsonBody } from './client'

interface ContractFileResponse {
  id: string
  original_name: string
  content_type: string
  size: number
  status: string
  created_at: string
}

interface TransportRentalResponse {
  id: string
  transport_id: string
  courier_id: string
  started_at: string
  ended_at: string | null
  file_id: string | null
  file: ContractFileResponse | null
  is_active: boolean
  created_at: string
  updated_at: string
}

interface TransportComponentResponse {
  id: string
  transport_id: string
  name: string
  unit_price: string
  quantity: number
  total_price: string
  created_at: string
  updated_at: string
}

interface TransportListItemResponse {
  id: string
  type: string
  model: string
  serial_number: string
  color: string
  deposit_required: boolean
  deposit_amount: string | null
  rental_price: string
  is_available: boolean
  created_at: string
  updated_at: string
}

interface TransportDetailResponse extends TransportListItemResponse {
  components: TransportComponentResponse[]
  active_rental: TransportRentalResponse | null
  comment: string | null
  debt_amount: string
}

interface PageResponse<T> {
  items: T[]
  next_cursor: string | null
}

function mapFile(file: ContractFileResponse): ContractFile {
  return {
    id: file.id,
    originalName: file.original_name,
    contentType: file.content_type,
    size: file.size,
    status: file.status,
    createdAt: file.created_at,
  }
}

export function mapRental(rental: TransportRentalResponse): TransportRental {
  return {
    id: rental.id,
    transportId: rental.transport_id,
    courierId: rental.courier_id,
    startedAt: rental.started_at,
    endedAt: rental.ended_at,
    fileId: rental.file_id,
    file: rental.file ? mapFile(rental.file) : null,
    isActive: rental.is_active,
    createdAt: rental.created_at,
    updatedAt: rental.updated_at,
  }
}

export function mapComponent(component: TransportComponentResponse): TransportComponent {
  return {
    id: component.id,
    transportId: component.transport_id,
    name: component.name,
    unitPrice: component.unit_price,
    quantity: component.quantity,
    totalPrice: component.total_price,
    createdAt: component.created_at,
    updatedAt: component.updated_at,
  }
}

export function mapTransportListItem(response: TransportListItemResponse): TransportListItem {
  return {
    id: response.id,
    type: response.type,
    model: response.model,
    serialNumber: response.serial_number,
    color: response.color,
    depositRequired: response.deposit_required,
    depositAmount: response.deposit_amount,
    rentalPrice: response.rental_price,
    isAvailable: response.is_available,
    createdAt: response.created_at,
    updatedAt: response.updated_at,
  }
}

function mapTransport(response: TransportDetailResponse): Transport {
  return {
    ...mapTransportListItem(response),
    components: response.components.map(mapComponent),
    activeRental: response.active_rental ? mapRental(response.active_rental) : null,
    comment: response.comment,
    debtAmount: response.debt_amount,
  }
}

function commandBody(value: unknown, key: string) {
  const request = jsonBody(value)
  const headers = new Headers(request.headers)
  headers.set('Idempotency-Key', key)
  return { ...request, headers }
}

function transportPayload(input: TransportInput, patch: boolean) {
  return {
    type: input.type.trim().toLowerCase(),
    model: input.model.trim(),
    serial_number: input.serialNumber.trim().toUpperCase(),
    color: input.color.trim(),
    deposit_required: input.depositRequired,
    ...(input.depositRequired
      ? { deposit_amount: input.depositAmount.trim() }
      : patch
        ? {}
        : { deposit_amount: null }),
    rental_price: input.rentalPrice.trim(),
    comment: input.comment.trim() || null,
    debt_amount: input.debtAmount.trim(),
  }
}

function transportPatch(input: TransportInput, current: Transport) {
  const normalized = transportPayload(input, true)
  const patch: Record<string, string | boolean | null> = {}
  if (normalized.type !== current.type) patch.type = normalized.type
  if (normalized.model !== current.model) patch.model = normalized.model
  if (normalized.serial_number !== current.serialNumber) patch.serial_number = normalized.serial_number
  if (normalized.color !== current.color) patch.color = normalized.color
  if (normalized.rental_price !== current.rentalPrice) patch.rental_price = normalized.rental_price
  if (normalized.comment !== current.comment) patch.comment = normalized.comment
  if (normalized.debt_amount !== current.debtAmount) patch.debt_amount = normalized.debt_amount
  if (input.depositRequired !== current.depositRequired) {
    patch.deposit_required = input.depositRequired
    if (input.depositRequired) patch.deposit_amount = input.depositAmount.trim()
  } else if (input.depositRequired && input.depositAmount.trim() !== current.depositAmount) {
    patch.deposit_amount = input.depositAmount.trim()
  }
  return patch
}

export async function listTransports(options: {
  cursor?: string | null
  limit: number
  filters: TransportFilters
}) {
  const params = new URLSearchParams({ limit: String(options.limit) })
  const type = options.filters.type.trim().toLowerCase()
  const serialNumber = options.filters.serialNumber.trim().toUpperCase()
  const courierId = options.filters.courierId.trim()
  if (type) params.set('type', type)
  if (serialNumber) params.set('serial_number', serialNumber)
  if (courierId) params.set('courier_id', courierId)
  if (options.filters.availability) {
    params.set('is_available', String(options.filters.availability === 'available'))
  }
  if (options.cursor) params.set('cursor', options.cursor)
  const response = await apiRequest<PageResponse<TransportListItemResponse>>(
    `/transport?${params.toString()}`,
  )
  return { items: response.items.map(mapTransportListItem), nextCursor: response.next_cursor }
}

export async function getTransport(id: string) {
  return mapTransport(await apiRequest<TransportDetailResponse>(`/transport/${id}`))
}

export async function createTransport(
  input: TransportInput,
  idempotencyKey: string = crypto.randomUUID(),
) {
  return mapTransport(
    await apiRequest<TransportDetailResponse>('/transport', {
      method: 'POST',
      ...commandBody(transportPayload(input, false), idempotencyKey),
    }),
  )
}

export async function updateTransport(id: string, input: TransportInput, current: Transport) {
  return mapTransport(
    await apiRequest<TransportDetailResponse>(`/transport/${id}`, {
      method: 'PATCH',
      ...jsonBody(transportPatch(input, current)),
    }),
  )
}

export function deleteTransport(id: string) {
  return apiRequest<void>(`/transport/${id}`, { method: 'DELETE' })
}

export async function createTransportComponent(
  transportId: string,
  input: TransportComponentInput,
  idempotencyKey: string = crypto.randomUUID(),
) {
  return mapComponent(
    await apiRequest<TransportComponentResponse>(`/transport/${transportId}/components`, {
      method: 'POST',
      ...commandBody(
        { name: input.name.trim(), unit_price: input.unitPrice, quantity: input.quantity },
        idempotencyKey,
      ),
    }),
  )
}

export async function updateTransportComponent(
  transportId: string,
  componentId: string,
  input: TransportComponentInput,
) {
  return mapComponent(
    await apiRequest<TransportComponentResponse>(
      `/transport/${transportId}/components/${componentId}`,
      {
        method: 'PATCH',
        ...jsonBody({ name: input.name.trim(), unit_price: input.unitPrice, quantity: input.quantity }),
      },
    ),
  )
}

export function deleteTransportComponent(transportId: string, componentId: string) {
  return apiRequest<void>(`/transport/${transportId}/components/${componentId}`, {
    method: 'DELETE',
  })
}

export async function listTransportRentals(
  transportId: string,
  options: { cursor?: string | null; limit: number },
) {
  const params = new URLSearchParams({ limit: String(options.limit) })
  if (options.cursor) params.set('cursor', options.cursor)
  const response = await apiRequest<PageResponse<TransportRentalResponse>>(
    `/transport/${transportId}/rentals?${params.toString()}`,
  )
  return { items: response.items.map(mapRental), nextCursor: response.next_cursor }
}

export async function getTransportRental(transportId: string, rentalId: string) {
  return mapRental(
    await apiRequest<TransportRentalResponse>(
      `/transport/${transportId}/rentals/${rentalId}`,
    ),
  )
}

export async function createTransportRental(
  transportId: string,
  input: TransportRentalInput,
  idempotencyKey: string = crypto.randomUUID(),
) {
  return mapRental(
    await apiRequest<TransportRentalResponse>(`/transport/${transportId}/rentals`, {
      method: 'POST',
      ...commandBody(
        {
          courier_id: input.courierId,
          started_at: input.startedAt,
          ended_at: input.endedAt,
          file_id: null,
        },
        idempotencyKey,
      ),
    }),
  )
}

export async function closeTransportRental(
  transportId: string,
  rentalId: string,
  endedAt: string,
  idempotencyKey: string = crypto.randomUUID(),
) {
  return mapRental(
    await apiRequest<TransportRentalResponse>(
      `/transport/${transportId}/rentals/${rentalId}/close`,
      {
        method: 'POST',
        ...commandBody({ ended_at: endedAt }, idempotencyKey),
      },
    ),
  )
}

export async function attachTransportContract(
  transportId: string,
  rentalId: string,
  fileId: string,
  idempotencyKey: string = crypto.randomUUID(),
) {
  return mapRental(
    await apiRequest<TransportRentalResponse>(
      `/transport/${transportId}/rentals/${rentalId}/contract`,
      {
        method: 'POST',
        ...commandBody({ file_id: fileId }, idempotencyKey),
      },
    ),
  )
}

export function transportErrorMessage(error: unknown, fallback: string) {
  if (error instanceof ApiError) {
    const messages: Record<string, string> = {
      'duplicate-serial-number': 'Велосипед с таким серийным номером уже существует.',
      'duplicate-component': 'Такая позиция уже есть в комплектации велосипеда.',
      'transport-rental-overlap': 'Велосипед уже выдан на часть выбранного периода.',
      'courier-rental-overlap': 'У курьера уже есть транспорт на часть выбранного периода.',
      'rental-already-closed': 'Эта аренда уже завершена.',
      'contract-already-attached': 'К этой аренде уже приложен договор. Заменить его нельзя.',
      'contract-file-in-use': 'Этот файл уже используется в другой аренде.',
      'file-not-ready': 'Файл договора ещё не готов.',
      'signed-contract-protects-rental': 'Велосипед нельзя удалить: в истории есть подписанный договор.',
      'invalid-deposit-state': 'Проверьте сумму и признак залога.',
      'payload-mismatch': 'Данные команды изменились при повторе. Отправьте форму ещё раз.',
      'in-flight': 'Команда уже выполняется. Повторите через несколько секунд.',
      'in-progress': 'Команда ещё выполняется. Повторите через несколько секунд.',
    }
    if (error.problem?.reason && messages[error.problem.reason]) {
      return messages[error.problem.reason]
    }
    if (error.status === 404) return 'Запись больше не существует.'
    if (error.status === 422) return 'Проверьте значения полей формы.'
  }
  return apiErrorMessage(error, fallback)
}
