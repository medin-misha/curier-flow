import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PixelCtaButton } from './PixelCtaButton'

function wrapper() {
  return screen.getByTestId('cta-wrap')
}

describe('PixelCtaButton', () => {
  it('изначально холодная', () => {
    render(<PixelCtaButton label="Оставить заявку" href="/apply" />)

    expect(wrapper()).toHaveAttribute('data-hot', 'false')
    expect(screen.getByRole('link', { name: 'Оставить заявку' })).toHaveAttribute('href', '/apply')
  })

  it('разогревается на наведении и остывает на уходе курсора', () => {
    render(<PixelCtaButton label="Оставить заявку" href="/apply" />)
    const link = screen.getByRole('link', { name: 'Оставить заявку' })

    fireEvent.mouseEnter(link)
    expect(wrapper()).toHaveAttribute('data-hot', 'true')

    fireEvent.mouseLeave(link)
    expect(wrapper()).toHaveAttribute('data-hot', 'false')
  })

  it('разогревается на фокусе с клавиатуры', () => {
    render(<PixelCtaButton label="Оставить заявку" href="/apply" />)
    const link = screen.getByRole('link', { name: 'Оставить заявку' })

    fireEvent.focus(link)
    expect(wrapper()).toHaveAttribute('data-hot', 'true')

    fireEvent.blur(link)
    expect(wrapper()).toHaveAttribute('data-hot', 'false')
  })

  it('прячет иконки от скринридеров', () => {
    render(<PixelCtaButton label="Оставить заявку" href="/apply" />)

    expect(screen.queryAllByRole('img')).toHaveLength(0)
  })
})

describe('PixelCtaButton на касании', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('держит подсветку 600 мс после отпускания пальца', () => {
    render(<PixelCtaButton label="Оставить заявку" href="/apply" />)
    const link = screen.getByRole('link', { name: 'Оставить заявку' })

    fireEvent.touchStart(link)
    expect(wrapper()).toHaveAttribute('data-hot', 'true')

    fireEvent.touchEnd(link)
    expect(wrapper()).toHaveAttribute('data-hot', 'true')

    act(() => {
      vi.advanceTimersByTime(600)
    })
    expect(wrapper()).toHaveAttribute('data-hot', 'false')
  })
})
