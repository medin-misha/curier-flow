import { render, renderHook, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useApplyWizard } from '../useApplyWizard'
import { StepIdentity } from './StepIdentity'

const TODAY = () => new Date(2026, 7, 14)

beforeEach(() => {
  vi.stubGlobal('scrollTo', vi.fn())
})

function setup() {
  const { result } = renderHook(() => useApplyWizard(TODAY))
  const view = render(<StepIdentity wizard={result.current} />)
  return { result, view }
}

describe('StepIdentity', () => {
  it('рисует заголовок и все поля шага', () => {
    setup()

    expect(screen.getByRole('heading', { name: 'Кто ты' })).toBeInTheDocument()
    expect(screen.getByLabelText(/Имя и фамилия/)).toBeInTheDocument()
    expect(screen.getByLabelText(/Дата рождения/)).toBeInTheDocument()
    expect(screen.getByLabelText(/Адрес проживания/)).toBeInTheDocument()
  })

  it('предлагает пять городов чипами', () => {
    setup()

    for (const city of ['Praha', 'Brno', 'Ostrava', 'Plzeň', 'Liberec']) {
      expect(screen.getByRole('button', { name: city })).toBeInTheDocument()
    }
  })

  it('выбор города чипом попадает в форму', async () => {
    const { result } = setup()

    await userEvent.click(screen.getByRole('button', { name: 'Brno' }))

    expect(result.current.form.city).toBe('Brno')
  })

  it('показывает подсказку по возрасту', () => {
    const { result, view } = setup()

    view.rerender(<StepIdentity wizard={{ ...result.current, form: { ...result.current.form, birthDate: '1998-03-10' } }} />)

    // Часы визарда застаблены на 14.08.2026, поэтому число лет точное.
    expect(screen.getByText('28 лет — подходит')).toBeInTheDocument()
  })
})
