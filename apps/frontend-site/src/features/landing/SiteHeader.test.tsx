import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Bike, Scene } from './scene.types'
import { SiteHeader } from './SiteHeader'

function bike(slug: string, name: string): Bike {
  return {
    slug,
    name,
    media: { poster: `/bikes/${slug}/poster.png`, focus: '50%' },
    specs: [
      { label: 'АКБ', value: '48V', note: 'заряд' },
      { label: 'ХОД', value: '65 км', note: 'запас' },
    ],
    description: ['текст'],
    price: { amount: 'от 1750 CZK', period: 'в неделю' },
  }
}

const intro: Scene = {
  kind: 'intro',
  id: 'i1',
  eyebrow: 'ПОДПИСЬ',
  title: 'Заголовок',
  background: { src: '/scenes/a.png', focusMobile: '50%', focusDesktop: '50%' },
  body: { kind: 'paragraphs', items: [['текст']] },
}

const scenes: Scene[] = [
  intro,
  { ...intro, id: 'i2' },
  { ...intro, id: 'i3' },
  { kind: 'bike', id: 'b1', bike: bike('urban-e1', 'MFS Urban E1') },
  { kind: 'bike', id: 'b2', bike: bike('cargo-x2', 'MFS Cargo X2') },
  {
    kind: 'gear',
    id: 'g1',
    eyebrow: 'ЭКИПИРОВКА',
    title: 'Сумка',
    image: { src: '/gear/bag.png', focus: '62%' },
    price: '750 CZK',
    backLabel: '↑ Назад к велосипеду',
  },
]

const scrollTo = vi.fn()

beforeEach(() => {
  scrollTo.mockClear()
  vi.stubGlobal('scrollTo', scrollTo)
  Object.defineProperty(window, 'innerHeight', { configurable: true, value: 800 })
})

describe('SiteHeader', () => {
  it('рисует три пункта меню', () => {
    render(<SiteHeader scenes={scenes} active={0} ctaVisible={false} />)

    expect(screen.getByRole('button', { name: 'Главная' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Транспорт' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Сумки' })).toBeInTheDocument()
  })

  it('подсвечивает «Транспорт» на каждом велосипеде', () => {
    const { rerender } = render(<SiteHeader scenes={scenes} active={3} ctaVisible />)
    expect(screen.getByRole('button', { name: 'Транспорт' })).toHaveAttribute('data-active', 'true')

    rerender(<SiteHeader scenes={scenes} active={4} ctaVisible />)
    expect(screen.getByRole('button', { name: 'Транспорт' })).toHaveAttribute('data-active', 'true')
  })

  it('показывает имя того велосипеда, что активен сейчас', () => {
    const { rerender } = render(<SiteHeader scenes={scenes} active={3} ctaVisible />)

    const name = screen.getByTestId('header-bike-name')
    expect(name).toHaveTextContent('MFS Urban E1')
    expect(name).toHaveAttribute('data-visible', 'true')

    rerender(<SiteHeader scenes={scenes} active={4} ctaVisible />)
    expect(screen.getByTestId('header-bike-name')).toHaveTextContent('MFS Cargo X2')

    rerender(<SiteHeader scenes={scenes} active={0} ctaVisible={false} />)
    expect(screen.getByTestId('header-bike-name')).toHaveAttribute('data-visible', 'false')
  })

  it('«Сумки» скроллит к сцене экипировки', async () => {
    render(<SiteHeader scenes={scenes} active={0} ctaVisible={false} />)

    await userEvent.click(screen.getByRole('button', { name: 'Сумки' }))

    expect(scrollTo).toHaveBeenCalledWith({ top: 4000, behavior: 'smooth' })
  })

  it('прячет CTA до второй сцены и убирает её из порядка табуляции', () => {
    const { rerender } = render(<SiteHeader scenes={scenes} active={0} ctaVisible={false} />)

    const hidden = screen.getByRole('link', { name: 'Оставить заявку' })
    expect(hidden).toHaveAttribute('data-visible', 'false')
    expect(hidden).toHaveAttribute('tabindex', '-1')

    rerender(<SiteHeader scenes={scenes} active={1} ctaVisible />)
    const shown = screen.getByRole('link', { name: 'Оставить заявку' })
    expect(shown).toHaveAttribute('data-visible', 'true')
    expect(shown).not.toHaveAttribute('tabindex')
  })
})
