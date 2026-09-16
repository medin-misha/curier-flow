import { describe, expect, it } from 'vitest'
import { activeNavKey, navTargets } from './sceneNavigation'
import type { Scene, TransportScene } from './scene.types'

function intro(id: string): Scene {
  return {
    kind: 'intro',
    id,
    eyebrow: 'ПОДПИСЬ',
    title: 'Заголовок',
    background: { src: '/scenes/a.png', focusMobile: '50%', focusDesktop: '50%' },
    body: { kind: 'paragraphs', items: [['текст']] },
  }
}

const transport: TransportScene = {
  kind: 'transport',
  id: 'transport',
  eyebrow: 'ЭЛЕКТРОТРАНСПОРТ',
  title: 'Электро-транспорт от 1500 CZK',
  media: { poster: '/transport/poster.png', focus: '50%' },
  description: ['текст'],
}

const scenes: Scene[] = [intro('i1'), intro('i2'), intro('i3'), transport]

describe('navTargets', () => {
  it('ведёт на единую сцену транспорта', () => {
    expect(navTargets(scenes)).toEqual([
      { key: 'home', label: 'Главная', index: 0 },
      { key: 'transport', label: 'Транспорт', index: 3 },
    ])
  })

  it('пропускает пункт, для которого нет сцены', () => {
    expect(navTargets([intro('i1')])).toEqual([
      { key: 'home', label: 'Главная', index: 0 },
    ])
  })
})

describe('activeNavKey', () => {
  it('подсвечивает «Транспорт» на единой сцене транспорта', () => {
    expect(activeNavKey(scenes, 3)).toBe('transport')
  })

  it('подсвечивает «Главная» на вводных сценах', () => {
    expect(activeNavKey(scenes, 0)).toBe('home')
    expect(activeNavKey(scenes, 2)).toBe('home')
  })

  it('на индексе вне массива возвращает «Главная»', () => {
    expect(activeNavKey(scenes, 99)).toBe('home')
  })
})
