import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { submitApplication } from './submitApplication'
import { useApplyWizard } from './useApplyWizard'

vi.mock('./submitApplication', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./submitApplication')>()
  return { ...actual, submitApplication: vi.fn(actual.submitApplication) }
})

const TODAY = () => new Date(2026, 7, 14)

function scan(name: string): File {
  return new File(['x'], name, { type: 'image/png' })
}

beforeEach(() => {
  vi.stubGlobal('scrollTo', vi.fn())
  vi.mocked(submitApplication).mockReset()
  vi.mocked(submitApplication).mockResolvedValue({
    ok: true,
    outcome: 'created',
    courierId: 'courier-1',
  })
})

function fillIdentity(result: { current: ReturnType<typeof useApplyWizard> }) {
  act(() => {
    result.current.setField('fullName', 'Ivan Ivanov')
    result.current.setField('birthDate', '1998-03-10')
    result.current.setField('city', 'Praha')
    result.current.setField('address', 'Malá Michnovka 1095/20')
  })
}

function fillContacts(result: { current: ReturnType<typeof useApplyWizard> }) {
  act(() => {
    result.current.setField('phone', '777123456')
    result.current.setField('email', 'ivan@email.com')
    result.current.setField('messengerContact', '+420 777 123 456')
  })
}

function fillDocuments(result: { current: ReturnType<typeof useApplyWizard> }) {
  act(() => {
    result.current.setField('bankAccount', 'CZ00 1234 5678')
    result.current.setField('citizenship', 'Украина')
    result.current.setFile('passport', scan('passport.png'))
    result.current.setFile('visa', scan('visa.png'))
  })
}

describe('useApplyWizard', () => {
  it('начинает с первого шага без ошибки', () => {
    const { result } = renderHook(() => useApplyWizard(TODAY))

    expect(result.current.step).toBe(1)
    expect(result.current.error).toBe('')
    expect(result.current.sent).toBe(false)
  })

  it('не пускает дальше и показывает ошибку шага', async () => {
    const { result } = renderHook(() => useApplyWizard(TODAY))

    await act(async () => {
      await result.current.next()
    })

    expect(result.current.step).toBe(1)
    expect(result.current.error).toBe('Впиши имя и фамилию.')
  })

  it('чистит ошибку при правке поля', async () => {
    const { result } = renderHook(() => useApplyWizard(TODAY))

    await act(async () => {
      await result.current.next()
    })
    expect(result.current.error).not.toBe('')

    act(() => result.current.setField('fullName', 'Ivan'))
    expect(result.current.error).toBe('')
  })

  it('оставляет в имени только латиницу и разделители', () => {
    const { result } = renderHook(() => useApplyWizard(TODAY))

    act(() => result.current.setField('fullName', "Iván Иванов 123 O'Neil-Novák"))

    expect(result.current.form.fullName).toBe("Iván   O'Neil-Novák")
  })

  it('подставляет телефон в контакт WhatsApp или @ для Telegram', () => {
    const { result } = renderHook(() => useApplyWizard(TODAY))

    act(() => result.current.setField('phone', '+420 777 123 456'))
    expect(result.current.form.messengerContact).toBe('+420777123456')

    act(() => result.current.setField('messenger', 'Telegram'))
    expect(result.current.form.messengerContact).toBe('@')

    act(() => result.current.setField('phone', '604 111 222'))
    expect(result.current.form.messengerContact).toBe('@')

    act(() => result.current.setField('messenger', 'WhatsApp'))
    expect(result.current.form.messengerContact).toBe('+420604111222')
  })

  it('оставляет в телефоне только цифры и режет до девяти', () => {
    const { result } = renderHook(() => useApplyWizard(TODAY))

    act(() => result.current.setField('phone', '+420 777 123 456 999'))

    expect(result.current.form.phone).toBe('777123456')
  })

  it('идёт вперёд по заполненным шагам и возвращается назад', async () => {
    const { result } = renderHook(() => useApplyWizard(TODAY))

    fillIdentity(result)
    await act(async () => {
      await result.current.next()
    })
    expect(result.current.step).toBe(2)

    act(() => result.current.back())
    expect(result.current.step).toBe(1)
  })

  it('не уходит раньше первого шага', () => {
    const { result } = renderHook(() => useApplyWizard(TODAY))

    act(() => result.current.back())

    expect(result.current.step).toBe(1)
  })

  it('перебрасывает на первый испорченный шаг при отправке', async () => {
    const { result } = renderHook(() => useApplyWizard(TODAY))

    fillIdentity(result)
    fillContacts(result)
    fillDocuments(result)
    act(() => result.current.goTo(4))
    act(() => result.current.setField('consent', true))

    // Пользователь вернулся и стёр почту уже после прохождения шага.
    act(() => result.current.setField('email', ''))

    await act(async () => {
      await result.current.next()
    })

    expect(result.current.step).toBe(2)
    expect(result.current.error).toBe('Проверь почту.')
    expect(result.current.sent).toBe(false)
  })

  it('отправляет заполненную заявку', async () => {
    const { result } = renderHook(() => useApplyWizard(TODAY))

    fillIdentity(result)
    fillContacts(result)
    fillDocuments(result)
    act(() => result.current.goTo(4))
    act(() => result.current.setField('consent', true))

    await act(async () => {
      await result.current.next()
    })

    await waitFor(() => expect(result.current.sent).toBe(true))
    expect(result.current.submissionOutcome).toBe('created')
    expect(result.current.error).toBe('')
    expect(result.current.submitting).toBe(false)
  })

  it('не отправляет заявку дважды при двойном нажатии', async () => {
    vi.mocked(submitApplication).mockClear()

    const { result } = renderHook(() => useApplyWizard(TODAY))

    fillIdentity(result)
    fillContacts(result)
    fillDocuments(result)
    act(() => result.current.goTo(4))
    act(() => result.current.setField('consent', true))

    await act(async () => {
      await Promise.all([result.current.next(), result.current.next()])
    })

    expect(vi.mocked(submitApplication)).toHaveBeenCalledTimes(1)
    await waitFor(() => expect(result.current.sent).toBe(true))
  })

  it('не запирает форму, если отправка упала с ошибкой', async () => {
    vi.mocked(submitApplication).mockClear()
    vi.mocked(submitApplication).mockRejectedValueOnce(new Error('network down'))

    const { result } = renderHook(() => useApplyWizard(TODAY))

    fillIdentity(result)
    fillContacts(result)
    fillDocuments(result)
    act(() => result.current.goTo(4))
    act(() => result.current.setField('consent', true))

    await act(async () => {
      await result.current.next()
    })

    expect(result.current.sent).toBe(false)
    expect(result.current.submitting).toBe(false)
    expect(result.current.error).toBe(
      'Не удалось отправить заявку. Проверь соединение и попробуй ещё раз.',
    )

    // Форма должна остаться рабочей: вторая попытка проходит.
    await act(async () => {
      await result.current.next()
    })
    await waitFor(() => expect(result.current.sent).toBe(true))
  })

  it('показывает problem-сообщение transport и оставляет форму открытой', async () => {
    vi.mocked(submitApplication).mockResolvedValueOnce({
      ok: false,
      message: 'Не удалось проверить данные заявки. Проверь поля и документы.',
    })
    const { result } = renderHook(() => useApplyWizard(TODAY))

    fillIdentity(result)
    fillContacts(result)
    fillDocuments(result)
    act(() => result.current.goTo(4))
    act(() => result.current.setField('consent', true))

    await act(async () => {
      await result.current.next()
    })

    expect(result.current.sent).toBe(false)
    expect(result.current.error).toBe(
      'Не удалось проверить данные заявки. Проверь поля и документы.',
    )
  })

  it('чистит ошибку при выборе файла', async () => {
    const { result } = renderHook(() => useApplyWizard(TODAY))

    fillIdentity(result)
    fillContacts(result)
    act(() => result.current.goTo(3))
    await act(async () => {
      await result.current.next()
    })
    expect(result.current.error).toBe('Впиши счёт в чешском банке.')

    act(() => result.current.setFile('passport', scan('passport.png')))
    expect(result.current.error).toBe('')
  })
})
