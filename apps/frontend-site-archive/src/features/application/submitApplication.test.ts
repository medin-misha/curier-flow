import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { emptyForm } from './form.types'
import { submitApplication, toCourierPayload, toFormData } from './submitApplication'

const passport = new File(['x'], 'passport.png', { type: 'image/png' })
const visa = new File(['x'], 'permit.pdf', { type: 'application/pdf' })

const payload = {
  form: {
    ...emptyForm,
    fullName: '  Ivan Ivanov  ',
    birthDate: '1998-03-10',
    city: ' Praha ',
    address: ' Karlova 1 ',
    phone: '777123456',
    email: ' ivan@email.com ',
    messenger: 'Telegram' as const,
    messengerContact: ' @ivan ',
    bankAccount: ' CZ00 1234 5678 ',
    citizenship: 'Украина',
    consent: true,
  },
  files: { passport, visa },
}

describe('toCourierPayload', () => {
  it('форматирует имя и фамилию перед отправкой', () => {
    expect(toCourierPayload({ ...payload.form, fullName: '  iVAN iVANov  ' }).full_name).toBe(
      'Ivan Ivanov',
    )
    expect(toCourierPayload({ ...payload.form, fullName: "o'NEIL-smITH" }).full_name).toBe(
      "O'Neil-Smith",
    )
  })

  it('переводит форму в backend DTO', () => {
    expect(toCourierPayload(payload.form)).toEqual({
      full_name: 'Ivan Ivanov',
      email: 'ivan@email.com',
      phone: '+420777123456',
      date_of_birth: '1998-03-10',
      city: 'Praha',
      address: 'Karlova 1',
      citizenship: 'Украина',
      bank_account: 'CZ00 1234 5678',
      contact_platform: 'telegram',
      contact: '@ivan',
      source: 'mfs_landing',
      consent_to_processing: true,
      platform_accounts: [{ platform: 'bolt_food' }],
      documents: [
        { type: 'passport', purpose: 'platform_onboarding' },
        { type: 'residence_permit', purpose: 'platform_onboarding' },
      ],
    })
  })

  it('отправляет два документа identity card для гражданина Чехии', () => {
    expect(toCourierPayload({ ...payload.form, citizenship: 'Чехия' }).documents).toEqual([
      { type: 'identity_card', purpose: 'platform_onboarding' },
      { type: 'identity_card', purpose: 'platform_onboarding' },
    ])
  })
})

describe('toFormData', () => {
  it('кладёт backend DTO JSON-строкой в payload', () => {
    const data = toFormData(payload)

    expect(JSON.parse(String(data.get('payload')))).toEqual(toCourierPayload(payload.form))
  })

  it('кладёт оба скана под files в порядке metadata', () => {
    const data = toFormData(payload)

    expect(data.getAll('files')).toEqual([passport, visa])
    expect(Array.from(data.keys())).toEqual(['payload', 'files', 'files'])
  })

  it('пропускает незагруженные файлы', () => {
    const data = toFormData({ form: emptyForm, files: { passport: null, visa: null } })

    expect(data.getAll('files')).toEqual([])
  })
})

const fetchMock = vi.fn<typeof fetch>()

function apiResponse(status: number, body: unknown): Response {
  return {
    status,
    json: vi.fn().mockResolvedValue(body),
  } as unknown as Response
}

describe('submitApplication', () => {
  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('отправляет multipart на same-origin endpoint без ручного Content-Type', async () => {
    fetchMock.mockResolvedValue(apiResponse(201, { id: 'courier-1' }))

    await expect(submitApplication(payload)).resolves.toEqual({
      ok: true,
      outcome: 'created',
      courierId: 'courier-1',
    })

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/courier')
    expect(init?.method).toBe('POST')
    expect(init?.body).toBeInstanceOf(FormData)
    expect(init?.headers).toBeUndefined()
  })

  it('отличает сохранённый aggregate по ответу 200', async () => {
    fetchMock.mockResolvedValue(apiResponse(200, { id: 'courier-1' }))

    await expect(submitApplication(payload)).resolves.toEqual({
      ok: true,
      outcome: 'existing',
      courierId: 'courier-1',
    })
  })

  it('переводит problem+json в сообщение формы', async () => {
    fetchMock.mockResolvedValue(apiResponse(409, { reason: 'identity-split' }))

    await expect(submitApplication(payload)).resolves.toEqual({
      ok: false,
      message:
        'Почта и телефон уже связаны с разными заявками. Напиши нам, чтобы проверить данные.',
    })
  })

  it.each([
    [422, { reason: 'file_too_large' }, 'Документы слишком большие. Каждый файл должен быть не больше 10 МБ.'],
    [
      500,
      { detail: 'Internal server error' },
      'Сервис временно недоступен. Попробуй отправить заявку позже.',
    ],
  ])('обрабатывает backend-ошибку %s', async (status, problem, message) => {
    fetchMock.mockResolvedValue(apiResponse(status, problem))

    await expect(submitApplication(payload)).resolves.toEqual({ ok: false, message })
  })

  it('не принимает успешный статус без courier id', async () => {
    fetchMock.mockResolvedValue(apiResponse(201, {}))

    await expect(submitApplication(payload)).resolves.toEqual({
      ok: false,
      message: 'Сервис вернул неполный ответ. Попробуй отправить заявку ещё раз.',
    })
  })

  it('оставляет сетевую ошибку вызывающему коду', async () => {
    fetchMock.mockRejectedValue(new TypeError('network down'))

    await expect(submitApplication(payload)).rejects.toThrow('network down')
  })
})
