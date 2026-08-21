import { describe, expect, it } from 'vitest'
import type { Bike } from '@/features/landing/scene.types'
import { activeNavKey, lastBikeIndex, navTargets } from '@/features/landing/sceneNavigation'
import { sceneEyebrow } from '@/features/landing/sceneEyebrow'
import { bikes } from './bikes'
import { composeScenes, scenes } from './scenes'

const secondBike: Bike = {
  slug: 'cargo-x2',
  name: 'MFS Cargo X2',
  media: { poster: '/bikes/cargo-x2/poster.png', focus: '55%' },
  specs: [
    { label: 'АКБ', value: '48V · 30Ah', note: 'зарядка 6 часов' },
    { label: 'ЗАПАС ХОДА', value: 'до 90 км', note: 'на одном заряде' },
  ],
  description: ['Грузовой электровелосипед для крупных заказов.'],
  price: { amount: 'от 2400 CZK', period: 'в неделю' },
}

describe('порядок сцен', () => {
  it('идёт от вводных к велосипедам и заканчивается экипировкой', () => {
    expect(scenes.map((scene) => scene.kind)).toEqual([
      'intro',
      'intro',
      'intro',
      ...bikes.map(() => 'bike' as const),
      'gear',
    ])
  })

  it('нумерует подписи по позиции: экипировка идёт последней', () => {
    const gearIndex = scenes.findIndex((scene) => scene.kind === 'gear')

    expect(gearIndex).toBe(scenes.length - 1)
    expect(sceneEyebrow(gearIndex, 'ЭКИПИРОВКА')).toContain(`${scenes.length} / `)
  })
})

describe('добавление велосипеда', () => {
  const withExtra = composeScenes([...bikes, secondBike])

  it('реальный порядок сцен строится из всего списка велосипедов', () => {
    expect(scenes.filter((scene) => scene.kind === 'bike')).toHaveLength(bikes.length)
  })

  it('даёт ровно на одну сцену больше', () => {
    expect(withExtra).toHaveLength(scenes.length + 1)
  })

  it('сдвигает экипировку в конец и её номер вместе с ней', () => {
    const gearIndex = withExtra.findIndex((scene) => scene.kind === 'gear')

    expect(gearIndex).toBe(withExtra.length - 1)
    expect(sceneEyebrow(gearIndex, 'ЭКИПИРОВКА')).toBe(
      `${String(withExtra.length).padStart(2, '0')} / ЭКИПИРОВКА`,
    )
    expect(navTargets(withExtra).find((target) => target.key === 'gear')?.index).toBe(gearIndex)
  })

  it('оставляет «Транспорт» на первом велосипеде и подсвечивает его на всех', () => {
    const firstBike = withExtra.findIndex((scene) => scene.kind === 'bike')
    const lastBike = withExtra.findLastIndex((scene) => scene.kind === 'bike')

    expect(navTargets(withExtra).find((target) => target.key === 'transport')?.index).toBe(firstBike)
    for (let index = firstBike; index <= lastBike; index += 1) {
      expect(activeNavKey(withExtra, index)).toBe('transport')
    }
  })

  it('ведёт «Назад к велосипеду» на последний велосипед', () => {
    expect(lastBikeIndex(withExtra)).toBe(withExtra.findLastIndex((s) => s.kind === 'bike'))
    expect(lastBikeIndex(withExtra)).toBeGreaterThan(
      withExtra.findIndex((s) => s.kind === 'bike'),
    )
  })
})
