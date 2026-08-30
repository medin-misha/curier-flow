import type { ApplicationFiles, ApplicationForm } from './form.types'
import { digitsOnly } from './validation'

export interface ApplicationPayload {
  form: ApplicationForm
  files: ApplicationFiles
}

type DeliveryPlatform = 'bolt_food'
type DocumentPurpose = 'platform_onboarding'
type DocumentType = 'passport' | 'residence_permit'

interface CourierDocumentCreate {
  type: DocumentType
  purpose: DocumentPurpose
}

/** Контракт JSON-part `payload` ручки POST /courier. */
export interface CourierCreatePayload {
  full_name: string
  email: string
  phone: string
  date_of_birth: string
  city: string
  address: string
  citizenship: string
  bank_account: string
  contact_platform: string
  contact: string
  source: 'mfs_landing'
  consent_to_processing: boolean
  platform_accounts: Array<{ platform: DeliveryPlatform }>
  documents: CourierDocumentCreate[]
}

export type SubmitResult =
  | { ok: true; outcome: 'created' | 'existing'; courierId: string }
  | { ok: false; message: string }

interface ProblemDetails {
  status?: unknown
  detail?: unknown
  reason?: unknown
}

const ENDPOINT = '/api/courier'
const REQUEST_TIMEOUT_MS = 60_000

/** Переводит UI-модель в неизменяемый backend-контракт. */
export function toCourierPayload(form: ApplicationForm): CourierCreatePayload {
  return {
    full_name: form.fullName.trim(),
    email: form.email.trim(),
    phone: `+420${digitsOnly(form.phone)}`,
    date_of_birth: form.birthDate,
    city: form.city.trim(),
    address: form.address.trim(),
    citizenship: form.citizenship.trim(),
    bank_account: form.bankAccount.trim(),
    contact_platform: form.messenger.toLowerCase(),
    contact: form.messengerContact.trim(),
    source: 'mfs_landing',
    consent_to_processing: form.consent,
    platform_accounts: [{ platform: 'bolt_food' }],
    documents: [
      { type: 'passport', purpose: 'platform_onboarding' },
      { type: 'residence_permit', purpose: 'platform_onboarding' },
    ],
  }
}

/** Собирает multipart: сначала JSON metadata, затем файлы в том же порядке. */
export function toFormData({ form, files }: ApplicationPayload): FormData {
  const data = new FormData()
  data.append('payload', JSON.stringify(toCourierPayload(form)))

  if (files.passport) data.append('files', files.passport)
  if (files.visa) data.append('files', files.visa)

  return data
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

async function responseJson(response: Response): Promise<unknown> {
  try {
    return await response.json()
  } catch {
    return null
  }
}

function problemMessage(status: number, body: ProblemDetails | null): string {
  const reason = typeof body?.reason === 'string' ? body.reason : ''

  if (reason === 'identity-split') {
    return 'Почта и телефон уже связаны с разными заявками. Напиши нам, чтобы проверить данные.'
  }
  if (reason === 'content-type-not-allowed') {
    return 'Формат документа не поддерживается. Загрузи PNG, JPEG, WebP или PDF.'
  }
  if (reason === 'empty_file') return 'Один из документов пуст. Выбери файл ещё раз.'
  if (reason === 'file_too_large' || reason === 'total_upload_too_large' || status === 413) {
    return 'Документы слишком большие. Каждый файл должен быть не больше 10 МБ.'
  }
  if (status === 422) return 'Не удалось проверить данные заявки. Проверь поля и документы.'
  if (status === 429) return 'Слишком много попыток. Подожди немного и отправь заявку снова.'
  if (status >= 500) return 'Сервис временно недоступен. Попробуй отправить заявку позже.'

  return 'Не удалось отправить заявку. Проверь данные и попробуй ещё раз.'
}

/** Отправляет заявку через same-origin proxy на backend POST /courier. */
export async function submitApplication(payload: ApplicationPayload): Promise<SubmitResult> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)

  try {
    const response = await fetch(ENDPOINT, {
      method: 'POST',
      body: toFormData(payload),
      signal: controller.signal,
    })
    const body = await responseJson(response)

    if (response.status === 200 || response.status === 201) {
      if (!isRecord(body) || typeof body.id !== 'string') {
        return {
          ok: false,
          message: 'Сервис вернул неполный ответ. Попробуй отправить заявку ещё раз.',
        }
      }
      return {
        ok: true,
        outcome: response.status === 201 ? 'created' : 'existing',
        courierId: body.id,
      }
    }

    return {
      ok: false,
      message: problemMessage(response.status, isRecord(body) ? body : null),
    }
  } finally {
    window.clearTimeout(timeout)
  }
}
