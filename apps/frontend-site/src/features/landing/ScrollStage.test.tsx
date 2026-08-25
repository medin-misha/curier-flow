import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Bike, Scene } from './scene.types'
import { ScrollStage } from './ScrollStage'

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

const gear: Scene = {
  kind: 'gear',
  id: 'g1',
  eyebrow: 'ЭКИПИРОВКА',
  title: 'Сумка',
  image: { src: '/gear/bag.png', focus: '62%' },
  price: '750 CZK',
  backLabel: '↑ Назад к велосипеду',
}

const twoBikes: Scene[] = [
  intro,
  { kind: 'bike', id: 'b1', bike: bike('urban-e1', 'MFS Urban E1') },
  { kind: 'bike', id: 'b2', bike: bike('cargo-x2', 'MFS Cargo X2') },
  gear,
]

beforeEach(() => {
  Object.defineProperty(window, 'innerHeight', { configurable: true, value: 800 })
  Object.defineProperty(window, 'scrollY', { configurable: true, value: 0 })
  Object.defineProperty(HTMLMediaElement.prototype, 'play', {
    configurable: true,
    writable: true,
    value: vi.fn(() => Promise.resolve()),
  })
})

describe('ScrollStage', () => {
  it('заводит по точке на каждую сцену, сколько бы их ни было', () => {
    const oneBike: Scene[] = [
      intro,
      { kind: 'bike', id: 'b1', bike: bike('urban-e1', 'MFS Urban E1') },
      gear,
    ]

    const { unmount } = render(<ScrollStage scenes={oneBike} />)
    expect(screen.getByTestId('scene-dots').children).toHaveLength(3)
    unmount()

    render(<ScrollStage scenes={twoBikes} />)
    expect(screen.getByTestId('scene-dots').children).toHaveLength(4)
  })

  it('продолжает нумерацию сцен подписью футера, сколько бы сцен ни было', () => {
    const oneBike: Scene[] = [
      intro,
      { kind: 'bike', id: 'b1', bike: bike('urban-e1', 'MFS Urban E1') },
      gear,
    ]

    const { unmount } = render(<ScrollStage scenes={oneBike} />)
    expect(screen.getByRole('contentinfo')).toHaveTextContent('04 / КОНТАКТЫ')
    unmount()

    render(<ScrollStage scenes={twoBikes} />)
    expect(screen.getByRole('contentinfo')).toHaveTextContent('05 / КОНТАКТЫ')
  })

  it('задаёт высоту трека по числу сцен', () => {
    render(<ScrollStage scenes={twoBikes} />)

    // Проверяем data-атрибут: jsdom не разбирает единицу dvh в inline-стиле.
    expect(screen.getByTestId('scroll-track')).toHaveAttribute('data-scene-count', '4')
  })

  it('рисует оба велосипеда', () => {
    render(<ScrollStage scenes={twoBikes} />)

    expect(screen.getByTestId('bike-layer-b1')).toBeInTheDocument()
    expect(screen.getByTestId('bike-layer-b2')).toBeInTheDocument()
  })

  it('выносит экипировку за пределы sticky-вьюпорта', () => {
    render(<ScrollStage scenes={twoBikes} />)

    const viewport = screen.getByTestId('scroll-viewport')
    expect(viewport).not.toContainElement(screen.getByTestId('gear-wrap-g1'))
  })

  it('на первой сцене прячет CTA и рисует футер', () => {
    render(<ScrollStage scenes={twoBikes} />)

    expect(screen.getAllByRole('link', { name: 'Оставить заявку' })[0]).toHaveAttribute(
      'data-visible',
      'false',
    )
    expect(screen.getByRole('contentinfo')).toBeInTheDocument()
  })

  it('возврат из экипировки ведёт на последний велосипед', async () => {
    const scrollTo = vi.fn()
    vi.stubGlobal('scrollTo', scrollTo)

    render(<ScrollStage scenes={twoBikes} />)

    await userEvent.click(screen.getByRole('button', { name: '↑ Назад к велосипеду' }))

    // Последний велосипед — индекс 2 в twoBikes, высота окна застаблена в 800.
    expect(scrollTo).toHaveBeenCalledWith({ top: 1600, behavior: 'smooth' })
  })
})
