import { act, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Scene, TransportScene } from './scene.types'
import { ScrollStage } from './ScrollStage'

const intro: Scene = {
  kind: 'intro',
  id: 'i1',
  eyebrow: 'ПОДПИСЬ',
  title: 'Заголовок',
  background: { src: '/scenes/a.png', focusMobile: '50%', focusDesktop: '50%' },
  body: { kind: 'paragraphs', items: [['текст']] },
}

const transport: TransportScene = {
  kind: 'transport',
  id: 'transport',
  eyebrow: 'ЭЛЕКТРОТРАНСПОРТ',
  title: 'Электро-транспорт от 1500 CZK',
  media: { poster: '/transport/poster.png', focus: '50%' },
  description: ['Электротранспорт для работы курьером.'],
}

const scenes: Scene[] = [intro, { ...intro, id: 'i2' }, { ...intro, id: 'i3' }, transport]

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
  it('рисует одну сцену электро-транспорта после вводных сцен', () => {
    render(<ScrollStage scenes={scenes} />)

    expect(screen.getByTestId('transport-layer-transport')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Электро-транспорт от 1500 CZK' })).toBeInTheDocument()
    expect(screen.queryByText('MFS Urban E1')).not.toBeInTheDocument()
  })

  it('прячет подсказку только после достижения контактов', () => {
    const getBoundingClientRect = vi
      .spyOn(HTMLElement.prototype, 'getBoundingClientRect')
      .mockReturnValue({ bottom: 3200 } as DOMRect)

    render(<ScrollStage scenes={scenes} />)
    const hint = screen.getByText('листай ↓')
    expect(hint).toHaveAttribute('data-hidden', 'false')

    getBoundingClientRect.mockReturnValue({ bottom: 800 } as DOMRect)
    act(() => {
      window.dispatchEvent(new Event('scroll'))
    })

    expect(hint).toHaveAttribute('data-hidden', 'true')
    getBoundingClientRect.mockRestore()
  })

  it('заводит по точке на каждую сцену', () => {
    render(<ScrollStage scenes={scenes} />)

    expect(screen.getByTestId('scene-dots').children).toHaveLength(4)
  })

  it('продолжает нумерацию сцен подписью футера', () => {
    render(<ScrollStage scenes={scenes} />)

    expect(screen.getByRole('contentinfo')).toHaveTextContent('05 / КОНТАКТЫ')
  })

  it('задаёт высоту трека по числу сцен', () => {
    render(<ScrollStage scenes={scenes} />)

    // Проверяем data-атрибут: jsdom не разбирает единицу dvh в inline-стиле.
    expect(screen.getByTestId('scroll-track')).toHaveAttribute('data-scene-count', '4')
  })

  it('на первой сцене прячет CTA и рисует футер', () => {
    render(<ScrollStage scenes={scenes} />)

    expect(screen.getAllByRole('link', { name: 'Оставить заявку' })[0]).toHaveAttribute(
      'data-visible',
      'false',
    )
    expect(screen.getByRole('contentinfo')).toBeInTheDocument()
  })
})
