import { CZECH_CITIZENSHIP } from '@/content/application'
import { getMessages } from '@/i18n/messages'
import type { Locale } from '@/i18n/locales'
import type { ApplicationFiles, ApplicationForm } from './form.types'
import { digitsOnly } from './validation'

export interface ApplicationPayload {
  form: ApplicationForm
  files: ApplicationFiles
}

type DeliveryPlatform = 'bolt_food'
type DocumentPurpose = 'platform_onboarding'
type DocumentType = 'passport' | 'identity_card' | 'residence_permit'

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
const NAME_WORD_SEPARATORS = new Set([' ', '-', "'", '’'])

function formatFullName(value: string): string {
  let shouldCapitalize = true

  return Array.from(value.trim().toLocaleLowerCase('en-US'))
    .map((char) => {
      if (NAME_WORD_SEPARATORS.has(char)) {
        shouldCapitalize = true
        return char
      }

      if (!shouldCapitalize) return char
      shouldCapitalize = false
      return char.toLocaleUpperCase('en-US')
    })
    .join('')
}

/** Переводит UI-модель в неизменяемый backend-контракт. */
export function toCourierPayload(form: ApplicationForm): CourierCreatePayload {
  const isCzechCitizen = form.citizenship === CZECH_CITIZENSHIP

  return {
    full_name: formatFullName(form.fullName),
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
    documents: isCzechCitizen
      ? [
          { type: 'identity_card', purpose: 'platform_onboarding' },
          { type: 'identity_card', purpose: 'platform_onboarding' },
        ]
      : [
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

function problemMessage(status: number, body: ProblemDetails | null, locale: Locale): string {
  const copy = getMessages(locale).application.errors
  const reason = typeof body?.reason === 'string' ? body.reason : ''

  if (reason === 'identity-split') return copy.identitySplit
  if (reason === 'content-type-not-allowed') return copy.documentType
  if (reason === 'empty_file') return copy.emptyDocument
  if (reason === 'file_too_large' || reason === 'total_upload_too_large' || status === 413) {
    return copy.documentsLarge
  }
  if (status === 422) return copy.invalidPayload
  if (status === 429) return copy.tooManyAttempts
  if (status >= 500) return copy.unavailable

  return copy.generic
}

/** Отправляет заявку через same-origin proxy на backend POST /courier. */
export async function submitApplication(
  payload: ApplicationPayload,
  locale: Locale = 'ru',
): Promise<SubmitResult> {
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
          message: getMessages(locale).application.errors.incompleteResponse,
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
      message: problemMessage(response.status, isRecord(body) ? body : null, locale),
    }
  } finally {
    window.clearTimeout(timeout)
  }
}
