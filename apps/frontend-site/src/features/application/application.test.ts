import { describe, expect, it, vi } from 'vitest'
import { initialApplication, submitApplication, toFormData, validateApplication, validateFile, type Application, type Documents } from './application'

const form: Application = { ...initialApplication(), platform: 'bolt_food', fullName: 'Ivan Example', phone: '+420 (777) 123-456', email: 'ivan@example.test', birthDate: '2000-09-16', address: 'Test 1, Praha', contactPlatform: 'telegram', contact: '@example', bankAccount: '123456789/0100', citizenship: 'ua', source: 'Test', consent: true }
const documents: Documents = { identity: [new File(['front'], 'front.png', { type: 'image/png' }), new File(['extra'], 'extra.pdf', { type: 'application/pdf' })], residence: [new File(['visa'], 'visa.png', { type: 'image/png' })] }

describe('Контракт анкеты', () => {
  it('отправляет metadata и документы в одном и том же порядке', () => {
    const data = toFormData(form, documents)
    const payload = JSON.parse(data.get('payload') as string)
    expect(payload).toMatchObject({ full_name: 'Ivan Example', phone: '+420777123456', platform_accounts: [{ platform: 'bolt_food' }], consent_to_processing: true, source: 'Test' })
    expect(payload.documents).toEqual([{ type: 'passport', purpose: 'platform_onboarding' }, { type: 'passport', purpose: 'platform_onboarding' }, { type: 'residence_permit', purpose: 'platform_onboarding' }])
    expect(data.getAll('files').map(file => (file as File).name)).toEqual(['front.png', 'extra.pdf', 'visa.png'])
    expect(payload).not.toHaveProperty('desired_transport')
  })
  it('для граждан Чехии отправляет обе стороны ID-карты', () => {
    const payload = JSON.parse(toFormData({ ...form, citizenship: 'cz' }, documents).get('payload') as string)
    expect(payload.documents.every((document: {type: string}) => document.type === 'identity_card')).toBe(true)
  })
  it('проверяет реальные даты, возраст, контакты и согласие', () => {
    const today = new Date('2026-09-16T12:00:00')
    expect(validateApplication(form, documents, today)).toEqual({})
    expect(validateApplication({ ...form, birthDate: '2011-09-17', consent: false }, documents, today)).toMatchObject({ birthDate: 'invalidBirthDate', consent: 'consent' })
    expect(validateApplication({ ...form, birthDate: '2000-02-31' }, documents, today)).toHaveProperty('birthDate')
    expect(validateApplication({ ...form, birthDate: '1950-09-16' }, documents, today)).toHaveProperty('birthDate')
    expect(validateApplication({ ...form, email: 'ivan', phone: '+4201', contactPlatform: 'whatsapp', contact: '@user' }, documents, today)).toMatchObject({ phone: 'invalidPhone', email: 'invalidEmail', contact: 'invalidContact' })
  })
  it('не принимает пустые, недопустимые и слишком большие файлы', () => {
    expect(validateFile(new File([], 'empty.png', { type: 'image/png' }))).toBe('fileEmpty')
    expect(validateFile(new File(['x'], 'script.html', { type: 'text/html' }))).toBe('fileType')
    const large = new File(['x'], 'large.png', { type: 'image/png' })
    Object.defineProperty(large, 'size', { value: 26 * 1024 * 1024 })
    expect(validateFile(large)).toBe('fileLarge')
    expect(validateApplication(form, { identity: [], residence: [] })).toMatchObject({ identity: 'fileRequired', residence: 'fileRequired' })
  })
})

describe('Отправка', () => {
  it.each([[201, 'created'], [200, 'existing']] as const)('различает ответ %i', async (status, outcome) => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 'courier-id' }), { status }))
    expect(await submitApplication(form, documents, fetcher)).toEqual({ ok: true, outcome })
    expect(fetcher.mock.calls[0]?.[0]).toBe('/api/courier')
    expect(fetcher.mock.calls[0]?.[1]).not.toHaveProperty('headers')
  })
  it.each([[409, 'identity-split', 'conflict'], [413, '', 'filesLarge'], [422, 'content-type-not-allowed', 'fileType'], [429, '', 'rateLimit'], [503, '', 'server']] as const)('обрабатывает %i %s', async (status, reason, error) => {
    expect(await submitApplication(form, documents, vi.fn().mockResolvedValue(new Response(JSON.stringify({ reason }), { status })))).toEqual({ ok: false, error })
  })
  it('не показывает успех без подтверждённого id', async () => {
    expect(await submitApplication(form, documents, vi.fn().mockResolvedValue(new Response('{}', { status: 200 })))).toEqual({ ok: false, error: 'incomplete' })
  })
  it('позволяет повторить запрос после сетевой ошибки', async () => {
    const fetcher = vi.fn().mockRejectedValueOnce(new TypeError('offline')).mockResolvedValueOnce(new Response('{"id":"saved"}', { status: 201 }))
    expect(await submitApplication(form, documents, fetcher)).toEqual({ ok: false, error: 'connection' })
    expect(await submitApplication(form, documents, fetcher)).toEqual({ ok: true, outcome: 'created' })
  })
  it('прерывает запрос через 60 секунд', async () => {
    vi.useFakeTimers()
    try {
      const fetcher = vi.fn<typeof fetch>().mockImplementation((_url, init) => new Promise((_resolve, reject) => init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))))
      const result = submitApplication(form, documents, fetcher)
      await vi.advanceTimersByTimeAsync(60_000)
      expect(await result).toEqual({ ok: false, error: 'timeout' })
    } finally { vi.useRealTimers() }
  })
})
