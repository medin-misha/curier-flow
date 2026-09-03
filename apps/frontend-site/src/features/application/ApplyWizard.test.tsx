import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { UserEvent } from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApplyWizard } from './ApplyWizard'
import { submitApplication } from './submitApplication'

vi.mock('./submitApplication', () => ({ submitApplication: vi.fn() }))

beforeEach(() => {
  vi.stubGlobal('scrollTo', vi.fn())
  vi.mocked(submitApplication).mockReset()
  vi.mocked(submitApplication).mockImplementation(
    () =>
      new Promise((resolve) => {
        setTimeout(
          () => resolve({ ok: true, outcome: 'created', courierId: 'courier-1' }),
          50,
        )
      }),
  )
})

function scan(name: string): File {
  return new File(['x'], name, { type: 'image/png' })
}

/** Заполняет и проходит все четыре шага, останавливаясь на сводке (шаг 4). */
async function fillAllSteps(user: UserEvent): Promise<void> {
  await user.type(screen.getByLabelText(/Имя и фамилия/), 'Ivan Ivanov')
  await user.type(screen.getByLabelText(/Дата рождения/), '1998-03-10')
  await user.click(screen.getByRole('button', { name: 'Praha' }))
  await user.type(screen.getByLabelText(/Адрес проживания/), 'Malá Michnovka 1095/20')
  await user.click(screen.getByRole('button', { name: 'Далее' }))

  await user.type(screen.getByLabelText(/Чешский номер телефона/), '777123456')
  await user.type(screen.getByLabelText(/Почта/), 'ivan@email.com')
  await user.click(screen.getByRole('button', { name: 'Telegram' }))
  await user.type(screen.getByLabelText(/Контакт в Telegram/), 'ivan')
  await user.click(screen.getByRole('button', { name: 'Далее' }))

  await user.type(screen.getByLabelText(/Счёт в чешском банке/), 'CZ00 1234 5678')
  await user.selectOptions(screen.getByLabelText(/Гражданство/), 'Украина')
  await user.upload(screen.getByLabelText('Скан паспорта'), scan('passport.png'))
  await user.upload(screen.getByLabelText('Скан визы / ВНЖ'), scan('visa.png'))
  await user.click(screen.getByRole('button', { name: 'Далее' }))
}

describe('ApplyWizard', () => {
  it('открывается на первом шаге и показывает его номер', () => {
    render(<ApplyWizard />)

    expect(screen.getByRole('heading', { name: 'Кто ты?' })).toBeInTheDocument()
    expect(screen.getByTestId('step-counter')).toHaveTextContent('01')
    expect(screen.getByText('Личные данные')).toBeInTheDocument()
  })

  it('для гражданина Чехии показывает загрузку обеих сторон удостоверения', async () => {
    const user = userEvent.setup()
    render(<ApplyWizard />)

    await user.type(screen.getByLabelText(/Имя и фамилия/), 'Ivan Ivanov')
    await user.type(screen.getByLabelText(/Дата рождения/), '1998-03-10')
    await user.click(screen.getByRole('button', { name: 'Praha' }))
    await user.type(screen.getByLabelText(/Адрес проживания/), 'Karlova 1')
    await user.click(screen.getByRole('button', { name: 'Далее' }))

    await user.type(screen.getByLabelText(/Чешский номер телефона/), '777123456')
    await user.type(screen.getByLabelText(/Почта/), 'ivan@email.com')
    await user.click(screen.getByRole('button', { name: 'Далее' }))

    await user.selectOptions(screen.getByLabelText(/Гражданство/), 'Чехия')

    expect(screen.getByLabelText('Občanský průkaz – front side')).toBeInTheDocument()
    expect(screen.getByLabelText('Občanský průkaz – back side')).toBeInTheDocument()
    expect(screen.queryByLabelText('Скан паспорта')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Скан визы / ВНЖ')).not.toBeInTheDocument()
  })

  it('показывает английскую версию и локализованные языковые ссылки', async () => {
    render(<ApplyWizard locale="en" />)

    expect(screen.getByRole('heading', { name: 'About you' })).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Site language' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'RU' })).toHaveAttribute('href', '/apply')
    expect(screen.getByRole('link', { name: 'CZ' })).toHaveAttribute('href', '/cs/apply')

    await userEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Enter your first and last name.')
  })

  it('показывает чешскую версию первого шага', () => {
    render(<ApplyWizard locale="cs" />)

    expect(screen.getByRole('heading', { name: 'Kdo jsi' })).toBeInTheDocument()
    expect(screen.getByLabelText(/Jméno a příjmení/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Pokračovat' })).toBeInTheDocument()
  })

  it('не пускает дальше и показывает ошибку', async () => {
    render(<ApplyWizard />)

    await userEvent.click(screen.getByRole('button', { name: 'Далее' }))

    expect(screen.getByRole('alert')).toHaveTextContent('Впиши имя и фамилию.')
    expect(screen.getByRole('heading', { name: 'Кто ты?' })).toBeInTheDocument()
  })

  it('прячет кнопку «назад» на первом шаге', () => {
    render(<ApplyWizard />)

    expect(screen.queryByRole('button', { name: 'Назад' })).not.toBeInTheDocument()
  })

  it('предлагает добавить домен Gmail, пока в почте нет @', async () => {
    const user = userEvent.setup()
    render(<ApplyWizard />)

    await user.type(screen.getByLabelText(/Имя и фамилия/), 'Ivan Ivanov')
    await user.type(screen.getByLabelText(/Дата рождения/), '1998-03-10')
    await user.click(screen.getByRole('button', { name: 'Praha' }))
    await user.type(screen.getByLabelText(/Адрес проживания/), 'Karlova 1')
    await user.click(screen.getByRole('button', { name: 'Далее' }))

    const email = screen.getByLabelText(/Почта/)
    await user.type(email, 'ivan')
    expect(screen.getByRole('button', { name: /Добавить @gmail.com/ })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Добавить @gmail.com/ }))
    expect(email).toHaveValue('ivan@gmail.com')

    await user.clear(email)
    await user.type(email, 'ivan@example.com')
    expect(screen.queryByRole('button', { name: /Добавить @gmail.com/ })).not.toBeInTheDocument()
  })

  it('проходит все четыре шага и показывает экран успеха', async () => {
    const user = userEvent.setup()
    render(<ApplyWizard />)

    await fillAllSteps(user)

    expect(screen.getByRole('heading', { name: 'Проверь и отправь' })).toBeInTheDocument()
    expect(screen.getByText('+420 777123456')).toBeInTheDocument()

    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: 'Отправить заявку' }))

    await waitFor(
      () => expect(screen.getByRole('heading', { name: 'Заявка отправлена' })).toBeInTheDocument(),
      { timeout: 3000 },
    )
    expect(screen.getByText('Telegram')).toBeInTheDocument()
  })

  it('«Изм.» в сводке уводит на шаг, где правят эту строку', async () => {
    const user = userEvent.setup()
    render(<ApplyWizard />)

    await fillAllSteps(user)

    expect(screen.getByRole('heading', { name: 'Проверь и отправь' })).toBeInTheDocument()

    // Прыжок через два шага назад: строка «Имя» правится на первом.
    await user.click(screen.getByRole('button', { name: 'Изменить: Имя' }))
    expect(screen.getByRole('heading', { name: 'Кто ты?' })).toBeInTheDocument()
    expect(screen.getByLabelText(/Имя и фамилия/)).toHaveValue('Ivan Ivanov')

    // И строка «Счёт» — на третьем.
    await user.click(screen.getByRole('button', { name: 'Далее' }))
    await user.click(screen.getByRole('button', { name: 'Далее' }))
    await user.click(screen.getByRole('button', { name: 'Далее' }))
    await user.click(screen.getByRole('button', { name: 'Изменить: Счёт' }))
    expect(screen.getByRole('heading', { name: 'Документы и счёт' })).toBeInTheDocument()
  })

  it('показывает отдельный экран для уже зарегистрированной заявки', async () => {
    vi.mocked(submitApplication).mockResolvedValueOnce({
      ok: true,
      outcome: 'existing',
      courierId: 'courier-1',
    })
    const user = userEvent.setup()
    render(<ApplyWizard />)

    await fillAllSteps(user)
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: 'Отправить заявку' }))

    expect(
      await screen.findByRole('heading', { name: 'Заявка уже зарегистрирована' }),
    ).toBeInTheDocument()
  })

  it('на время отправки гасит кнопку и меняет надпись', async () => {
    const user = userEvent.setup()
    render(<ApplyWizard />)

    await fillAllSteps(user)
    await user.click(screen.getByRole('checkbox'))

    // Не ждём завершения: контролируем transport и проверяем промежуточное состояние.
    const submit = screen.getByRole('button', { name: 'Отправить заявку' })
    await user.click(submit)

    const pending = await screen.findByRole('button', { name: 'Отправляем…' })
    expect(pending).toBeDisabled()

    await waitFor(
      () => expect(screen.getByRole('heading', { name: 'Заявка отправлена' })).toBeInTheDocument(),
      { timeout: 3000 },
    )
  })
})
