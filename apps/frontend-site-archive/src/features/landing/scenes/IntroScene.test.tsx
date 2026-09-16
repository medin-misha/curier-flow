import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { IntroScene as IntroSceneData } from '../scene.types'
import { IntroScene } from './IntroScene'

const withBullets: IntroSceneData = {
  kind: 'intro',
  id: 'intro-offer',
  eyebrow: 'BOLT FOOD · CZ',
  title: 'Работай курьером Bolt Food в Чехии',
  background: { src: '/scenes/intro-1.png', focusMobile: '52%', focusDesktop: '70%' },
  align: 'top',
  body: {
    kind: 'bullets',
    items: [
      { marker: '—', markerKind: 'dash', text: ['Свой транспорт иметь необязательно'] },
      { marker: '—', markerKind: 'dash', text: ['Комиссия флотилии — всего ', { em: '10%' }] },
    ],
  },
  cta: { label: 'Оставить заявку', href: '/apply' },
}

const withParagraphs: IntroSceneData = {
  kind: 'intro',
  id: 'intro-bundle',
  eyebrow: 'ВСЁ В ОДНОМ МЕСТЕ',
  title: 'Подключение, транспорт и термо-сумка',
  background: { src: '/scenes/intro-3.png', focusMobile: '42%', focusDesktop: '60%' },
  body: { kind: 'paragraphs', items: [['Работаем по всей Чехии.']] },
}

describe('IntroScene', () => {
  it('нумерует подпись по позиции сцены', () => {
    render(<IntroScene scene={withBullets} index={0} active />)
    expect(screen.getByText('01 / BOLT FOOD · CZ')).toBeInTheDocument()
  })

  it('рисует заголовок, буллеты и выделения', () => {
    render(<IntroScene scene={withBullets} index={0} active />)

    expect(
      screen.getByRole('heading', { name: 'Работай курьером Bolt Food в Чехии' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Свой транспорт иметь необязательно')).toBeInTheDocument()
    expect(screen.getByText('10%').tagName).toBe('STRONG')
  })

  it('рисует CTA, когда она есть в сцене', () => {
    render(<IntroScene scene={withBullets} index={0} active />)
    expect(screen.getByRole('link', { name: 'Оставить заявку' })).toHaveAttribute('href', '/apply')
  })

  it('рисует абзацы и обходится без CTA', () => {
    render(<IntroScene scene={withParagraphs} index={2} active />)

    expect(screen.getByText('Работаем по всей Чехии.')).toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.getByText('03 / ВСЁ В ОДНОМ МЕСТЕ')).toBeInTheDocument()
  })

  it('помечает слой и текст неактивными', () => {
    render(<IntroScene scene={withParagraphs} index={2} active={false} />)

    expect(screen.getByTestId('intro-layer-intro-bundle')).toHaveAttribute('data-active', 'false')
    expect(screen.getByTestId('intro-content-intro-bundle')).toHaveAttribute('data-active', 'false')
  })

  it('помечает первой только сцену с нулевым индексом, независимо от активности', () => {
    const { rerender } = render(<IntroScene scene={withBullets} index={0} active={false} />)
    expect(screen.getByTestId('intro-content-intro-offer')).toHaveAttribute('data-first', 'true')

    rerender(<IntroScene scene={withParagraphs} index={2} active />)
    expect(screen.getByTestId('intro-content-intro-bundle')).toHaveAttribute('data-first', 'false')
  })

  it('неактивная сцена выключена для клавиатуры и мыши', () => {
    const { rerender } = render(<IntroScene scene={withBullets} index={0} active={false} />)
    expect(screen.getByTestId('intro-content-intro-offer')).toHaveAttribute('inert')

    rerender(<IntroScene scene={withBullets} index={0} active />)
    expect(screen.getByTestId('intro-content-intro-offer')).not.toHaveAttribute('inert')
  })
})
