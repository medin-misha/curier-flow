import type { CopyKey } from '../../content/i18n'

export interface Application {
  platform: '' | 'bolt_food'
  fullName: string
  city: string
  phone: string
  email: string
  birthDate: string
  address: string
  contactPlatform: '' | 'telegram' | 'whatsapp'
  contact: string
  bankAccount: string
  citizenship: string
  source: string
  consent: boolean
}
export interface Documents { identity: File[]; residence: File[] }
export type Field = keyof Application | keyof Documents
export type Errors = Partial<Record<Field, CopyKey>>

export function initialApplication(): Application {
  return { platform: '', fullName: '', city: 'Prague', phone: '+420', email: '', birthDate: '', address: '', contactPlatform: '', contact: '', bankAccount: '', citizenship: '', source: '', consent: false }
}
export const normalizePhone = (value: string) => value.replace(/[\s()-]/g, '')
export const MAX_FILE_SIZE = 25 * 1024 * 1024
const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf']
export function validateFile(file: File): CopyKey | undefined {
  if (!file.size) return 'fileEmpty'
  if (!ALLOWED_TYPES.includes(file.type)) return 'fileType'
  if (file.size > MAX_FILE_SIZE) return 'fileLarge'
}

export function validateApplication(form: Application, documents: Documents, today = new Date()): Errors {
  const errors: Errors = {}
  const required = ['platform', 'fullName', 'city', 'phone', 'email', 'birthDate', 'address', 'contactPlatform', 'contact', 'bankAccount', 'citizenship', 'source'] as const
  for (const field of required) if (!form[field].trim()) errors[field] = 'required'
  if (form.fullName && !/^[\p{Script=Latin}\p{M}]+(?:[ '\u2019-][\p{Script=Latin}\p{M}]+)+$/u.test(form.fullName.trim())) errors.fullName = 'invalidName'
  if (!/^\+420\d{9}$/.test(normalizePhone(form.phone))) errors.phone = 'invalidPhone'
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email.trim())) errors.email = 'invalidEmail'
  const birth = new Date(`${form.birthDate}T12:00:00`)
  let age = today.getFullYear() - birth.getFullYear()
  if (today.getMonth() < birth.getMonth() || (today.getMonth() === birth.getMonth() && today.getDate() < birth.getDate())) age--
  if (!/^\d{4}-\d{2}-\d{2}$/.test(form.birthDate) || Number.isNaN(birth.getTime()) || birth.toLocaleDateString('sv-SE') !== form.birthDate || age < 15 || age > 75) errors.birthDate = 'invalidBirthDate'
  if (form.contactPlatform === 'whatsapp' && !/^\+[1-9]\d{7,14}$/.test(normalizePhone(form.contact))) errors.contact = 'invalidContact'
  if (form.contactPlatform === 'telegram' && !/^@?[a-zA-Z0-9_]{5,32}$/.test(form.contact.trim())) errors.contact = 'invalidContact'
  const limits = { fullName: 255, city: 128, email: 320, address: 528, contact: 255, bankAccount: 64, citizenship: 128, source: 64 } as const
  for (const field of Object.keys(limits) as (keyof typeof limits)[]) if (form[field].trim().length > limits[field]) errors[field] = 'tooLong'
  for (const group of ['identity', 'residence'] as const) {
    if (!documents[group].length) errors[group] = 'fileRequired'
    for (const file of documents[group]) { const error = validateFile(file); if (error) errors[group] = error }
  }
  const files = [...documents.identity, ...documents.residence]
  if (files.length > 20 || files.reduce((size, file) => size + file.size, 0) > 90 * 1024 * 1024) errors.residence = 'filesLarge'
  if (!form.consent) errors.consent = 'consent'
  return errors
}

export function toFormData(form: Application, documents: Documents): FormData {
  const czech = form.citizenship === 'cz'
  const metadata = [
    ...documents.identity.map(() => ({ type: czech ? 'identity_card' : 'passport', purpose: 'platform_onboarding' })),
    ...documents.residence.map(() => ({ type: czech ? 'identity_card' : 'residence_permit', purpose: 'platform_onboarding' })),
  ]
  const data = new FormData()
  data.append('payload', JSON.stringify({
    full_name: form.fullName.trim(), email: form.email.trim(), phone: normalizePhone(form.phone),
    date_of_birth: form.birthDate, city: form.city.trim(), address: form.address.trim(),
    citizenship: form.citizenship, bank_account: form.bankAccount.trim(),
    contact_platform: form.contactPlatform, contact: form.contactPlatform === 'whatsapp' ? normalizePhone(form.contact) : form.contact.trim(),
    source: form.source.trim(), consent_to_processing: form.consent,
    platform_accounts: [{ platform: form.platform }], documents: metadata,
  }))
  for (const file of [...documents.identity, ...documents.residence]) data.append('files', file)
  return data
}

export type SubmitResult = { ok: true; outcome: 'created' | 'existing' } | { ok: false; error: CopyKey }
export function responseError(status: number, reason?: unknown): CopyKey {
  if (reason === 'identity-split' || status === 409) return 'conflict'
  if (reason === 'content-type-not-allowed') return 'fileType'
  if (reason === 'empty_file') return 'fileEmpty'
  if (reason === 'file_too_large') return 'fileLarge'
  if (reason === 'total_upload_too_large' || status === 413) return 'filesLarge'
  if (status === 429) return 'rateLimit'
  if (status >= 500) return 'server'
  return 'invalidPayload'
}
export async function submitApplication(form: Application, documents: Documents, fetcher: typeof fetch = fetch): Promise<SubmitResult> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 60_000)
  try {
    const response = await fetcher('/api/courier', { method: 'POST', body: toFormData(form, documents), signal: controller.signal })
    const body = await response.json().catch(() => null)
    if (response.status === 200 || response.status === 201) {
      if (!body || typeof body.id !== 'string' || !body.id) return { ok: false, error: 'incomplete' }
      return { ok: true, outcome: response.status === 201 ? 'created' : 'existing' }
    }
    return { ok: false, error: responseError(response.status, body?.reason) }
  } catch {
    return { ok: false, error: controller.signal.aborted ? 'timeout' : 'connection' }
  } finally { clearTimeout(timeout) }
}
