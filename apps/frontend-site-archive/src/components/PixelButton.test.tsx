import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { PixelButton, PixelLink } from './PixelButton'

describe('PixelButton', () => {
  it('рисует надпись и по умолчанию основной вариант', () => {
    render(<PixelButton>Далее</PixelButton>)

    const button = screen.getByRole('button', { name: 'Далее' })
    expect(button).toHaveAttribute('data-variant', 'primary')
    expect(button).toHaveAttribute('data-size', 'md')
  })

  it('прокидывает вариант, размер и обработчик', async () => {
    const onClick = vi.fn()
    render(
      <PixelButton variant="ghost" size="xs" onClick={onClick}>
        Назад
      </PixelButton>,
    )

    const button = screen.getByRole('button', { name: 'Назад' })
    expect(button).toHaveAttribute('data-variant', 'ghost')
    expect(button).toHaveAttribute('data-size', 'xs')

    await userEvent.click(button)
    expect(onClick).toHaveBeenCalledOnce()
  })
})

describe('PixelLink', () => {
  it('рисует ссылку с адресом', () => {
    render(
      <PixelLink href="/apply" variant="cta">
        Оставить заявку
      </PixelLink>,
    )

    const link = screen.getByRole('link', { name: 'Оставить заявку' })
    expect(link).toHaveAttribute('href', '/apply')
    expect(link).toHaveAttribute('data-variant', 'cta')
  })
})
