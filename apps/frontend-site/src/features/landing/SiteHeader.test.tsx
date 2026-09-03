import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { Scene, TransportScene } from './scene.types'
import { SiteHeader } from './SiteHeader'

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
  description: ['текст'],
}

const scenes: Scene[] = [intro, { ...intro, id: 'i2' }, { ...intro, id: 'i3' }, transport]

describe('SiteHeader', () => {
  it('рисует меню без страницы с сумками и названия компании', () => {
    render(<SiteHeader scenes={scenes} active={0} ctaVisible={false} />)

    expect(screen.getByRole('button', { name: 'Главная' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Транспорт' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Сумки' })).not.toBeInTheDocument()
    expect(screen.queryByText('May Fleet Solutions')).not.toBeInTheDocument()
  })

  it('подсвечивает «Транспорт» на единой сцене транспорта', () => {
    render(<SiteHeader scenes={scenes} active={3} ctaVisible />)

    expect(screen.getByRole('button', { name: 'Транспорт' })).toHaveAttribute('data-active', 'true')
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
