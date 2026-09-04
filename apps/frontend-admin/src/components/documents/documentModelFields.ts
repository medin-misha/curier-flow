import type { Courier } from '../../types/courier'
import type { DocumentModelGroup } from '../../types/document'
import type { Transport, TransportRental } from '../../types/transport'

type FieldReader<T> = (model: T) => string
type ModelFieldReaders<T> = Record<string, FieldReader<T>>

function text(value: string | number | null | undefined) {
  return value == null ? '' : String(value)
}

function yesNo(value: boolean) {
  return value ? 'Да' : 'Нет'
}

function date(value: string | null) {
  if (!value) return ''
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})/)
  return match ? `${match[3]}.${match[2]}.${match[1]}` : value
}

const courierFields: ModelFieldReaders<Courier> = {
  id: (courier) => courier.id,
  full_name: (courier) => courier.fullName,
  email: (courier) => courier.email,
  phone: (courier) => courier.phone,
  date_of_birth: (courier) => date(courier.birthDate),
  city: (courier) => text(courier.city),
  address: (courier) => text(courier.address),
  citizenship: (courier) => text(courier.citizenship),
  bank_account: (courier) => text(courier.bank),
  contact_platform: (courier) => text(courier.contactPlatform),
  contact: (courier) => text(courier.contact),
  source: (courier) => text(courier.source),
  consent_to_processing: (courier) => yesNo(courier.consent),
  consent_at: (courier) => date(courier.consentAt),
  created_at: (courier) => date(courier.createdAt),
  updated_at: (courier) => date(courier.updatedAt),
}

const transportFields: ModelFieldReaders<Transport> = {
  id: (transport) => transport.id,
  type: (transport) => transport.type,
  model: (transport) => transport.model,
  serial_number: (transport) => transport.serialNumber,
  color: (transport) => transport.color,
  deposit_required: (transport) => yesNo(transport.depositRequired),
  deposit_amount: (transport) => text(transport.depositAmount),
  rental_price: (transport) => transport.rentalPrice,
  comment: (transport) => text(transport.comment),
  debt_amount: (transport) => transport.debtAmount,
  is_available: (transport) => yesNo(transport.isAvailable),
  created_at: (transport) => date(transport.createdAt),
  updated_at: (transport) => date(transport.updatedAt),
}

const rentalFields: ModelFieldReaders<TransportRental> = {
  id: (rental) => rental.id,
  transport_id: (rental) => rental.transportId,
  courier_id: (rental) => rental.courierId,
  started_at: (rental) => date(rental.startedAt),
  ended_at: (rental) => date(rental.endedAt),
  file_id: (rental) => text(rental.fileId),
  is_active: (rental) => yesNo(rental.isActive),
  created_at: (rental) => date(rental.createdAt),
  updated_at: (rental) => date(rental.updatedAt),
}

export const documentModelFields = {
  courier: courierFields,
  transport: transportFields,
  transport_courier: rentalFields,
} satisfies Record<DocumentModelGroup, ModelFieldReaders<never>>

export function documentModelValues<T>(
  group: DocumentModelGroup,
  fields: string[],
  model: T,
) {
  const readers = documentModelFields[group] as ModelFieldReaders<T>
  return Object.fromEntries(
    fields.flatMap((field) => (readers[field] ? [[field, readers[field](model)]] : [])),
  )
}
