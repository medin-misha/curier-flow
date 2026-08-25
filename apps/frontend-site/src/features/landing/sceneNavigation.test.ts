import { describe, expect, it } from 'vitest'
import {
  activeBikeName,
  activeNavKey,
  lastBikeIndex,
  navTargets,
} from './sceneNavigation'
import type { Bike, Scene } from './scene.types'

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

function gear(id: string): Scene {
  return {
    kind: 'gear',
    id,
    eyebrow: 'ЭКИПИРОВКА',
    title: 'Сумка',
    image: { src: '/gear/bag.png', focus: '62%' },
    price: '750 CZK',
    backLabel: '↑ Назад к велосипеду',
  }
}

const oneBike: Scene[] = [
  intro('i1'),
  intro('i2'),
  intro('i3'),
  { kind: 'bike', id: 'b1', bike: bike('urban-e1', 'MFS Urban E1') },
  gear('g1'),
]

const twoBikes: Scene[] = [
  intro('i1'),
  intro('i2'),
  intro('i3'),
  { kind: 'bike', id: 'b1', bike: bike('urban-e1', 'MFS Urban E1') },
  { kind: 'bike', id: 'b2', bike: bike('cargo-x2', 'MFS Cargo X2') },
  gear('g1'),
]

describe('navTargets', () => {
  it('ведёт на первый велосипед и на экипировку', () => {
    expect(navTargets(oneBike)).toEqual([
      { key: 'home', label: 'Главная', index: 0 },
      { key: 'transport', label: 'Транспорт', index: 3 },
      { key: 'gear', label: 'Сумки', index: 4 },
    ])
  })

  it('со вторым велосипедом цель «Сумки» сдвигается, «Транспорт» — нет', () => {
    expect(navTargets(twoBikes)).toEqual([
      { key: 'home', label: 'Главная', index: 0 },
      { key: 'transport', label: 'Транспорт', index: 3 },
      { key: 'gear', label: 'Сумки', index: 5 },
    ])
  })

  it('пропускает пункт, для которого нет сцены', () => {
    expect(navTargets([intro('i1')])).toEqual([
      { key: 'home', label: 'Главная', index: 0 },
    ])
  })
})

describe('activeNavKey', () => {
  it('подсвечивает «Транспорт» на каждом велосипеде', () => {
    expect(activeNavKey(twoBikes, 3)).toBe('transport')
    expect(activeNavKey(twoBikes, 4)).toBe('transport')
  })

  it('подсвечивает «Сумки» на экипировке и «Главная» на вводных', () => {
    expect(activeNavKey(twoBikes, 5)).toBe('gear')
    expect(activeNavKey(twoBikes, 0)).toBe('home')
    expect(activeNavKey(twoBikes, 2)).toBe('home')
  })

  it('на индексе вне массива возвращает «Главная»', () => {
    expect(activeNavKey(twoBikes, 99)).toBe('home')
  })
})

describe('lastBikeIndex', () => {
  it('указывает на последний велосипед', () => {
    expect(lastBikeIndex(oneBike)).toBe(3)
    expect(lastBikeIndex(twoBikes)).toBe(4)
  })

  it('без велосипедов возвращает -1', () => {
    expect(lastBikeIndex([intro('i1'), gear('g1')])).toBe(-1)
  })
})

describe('activeBikeName', () => {
  it('отдаёт имя активного велосипеда', () => {
    expect(activeBikeName(twoBikes, 4)).toBe('MFS Cargo X2')
  })

  it('на не-велосипедной сцене отдаёт null', () => {
    expect(activeBikeName(twoBikes, 0)).toBeNull()
    expect(activeBikeName(twoBikes, 5)).toBeNull()
  })
})
