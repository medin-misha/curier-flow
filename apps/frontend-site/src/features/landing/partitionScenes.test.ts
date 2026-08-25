import { describe, expect, it } from 'vitest'
import { partitionScenes } from './partitionScenes'
import type { Scene } from './scene.types'

const intro: Scene = {
  kind: 'intro',
  id: 'i1',
  eyebrow: 'ПОДПИСЬ',
  title: 'Заголовок',
  background: { src: '/scenes/a.png', focusMobile: '50%', focusDesktop: '50%' },
  body: { kind: 'paragraphs', items: [['текст']] },
}

const bike: Scene = {
  kind: 'bike',
  id: 'b1',
  bike: {
    slug: 'urban-e1',
    name: 'MFS Urban E1',
    media: { poster: '/bikes/urban-e1/poster.png', focus: '58%' },
    specs: [
      { label: 'АКБ', value: '48V', note: 'заряд' },
      { label: 'ХОД', value: '65 км', note: 'запас' },
    ],
    description: ['текст'],
    price: { amount: 'от 1750 CZK', period: 'в неделю' },
  },
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

describe('partitionScenes', () => {
  it('уводит экипировку в оверлей, остальное оставляет на сцене', () => {
    const { stage, overlay } = partitionScenes([intro, bike, gear])

    expect(stage.map((entry) => entry.scene.id)).toEqual(['i1', 'b1'])
    expect(overlay.map((entry) => entry.scene.id)).toEqual(['g1'])
  })

  it('сохраняет исходные индексы сцен', () => {
    const { stage, overlay } = partitionScenes([intro, bike, gear])

    expect(stage.map((entry) => entry.index)).toEqual([0, 1])
    expect(overlay[0].index).toBe(2)
  })
})
