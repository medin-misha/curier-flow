import { describe, expect, it } from 'vitest'
import { activeNavKey, navTargets } from '@/features/landing/sceneNavigation'
import { composeScenes, getScenes, scenes } from './scenes'

describe('порядок сцен', () => {
  it('идёт от трёх вводных сцен к единой сцене транспорта', () => {
    expect(scenes.map((scene) => scene.kind)).toEqual([
      'intro',
      'intro',
      'intro',
      'transport',
    ])
  })

  it('показывает новую информацию о комиссии и термосумке', () => {
    const offer = scenes[0]

    expect(offer.kind).toBe('intro')
    if (offer.kind !== 'intro' || offer.body.kind !== 'bullets') return

    expect(offer.body.items[1].text).toEqual(['Маленькая комиссия'])
    expect(offer.body.items[2].text).toEqual(['Мы можем предоставить термосумку'])
  })

  it('содержит общее предложение без данных конкретной модели', () => {
    const transport = scenes[3]

    expect(transport.kind).toBe('transport')
    if (transport.kind !== 'transport') return

    expect(transport.title).toBe('Электро-транспорт от 1500 CZK')
  })
})

describe('локализация сцен', () => {
  it('сохраняет одинаковый порядок и ID на всех языках', () => {
    const russian = getScenes('ru')

    for (const locale of ['en', 'cs'] as const) {
      expect(getScenes(locale).map((scene) => [scene.kind, scene.id])).toEqual(
        russian.map((scene) => [scene.kind, scene.id]),
      )
    }
  })

  it('локализует контент и адрес заявки', () => {
    const english = getScenes('en')[0]
    const czech = getScenes('cs')[0]

    expect(english.kind === 'intro' ? english.title : '').toBe(
      'Work as a Bolt Food courier in Czechia',
    )
    expect(english.kind === 'intro' ? english.cta?.href : '').toBe('/en/apply')
    expect(czech.kind === 'intro' ? czech.title : '').toBe(
      'Pracuj jako kurýr Bolt Food v Česku',
    )
    expect(czech.kind === 'intro' ? czech.cta?.href : '').toBe('/cs/apply')
  })

  it('локализует единую сцену транспорта', () => {
    const english = getScenes('en')[3]
    const czech = getScenes('cs')[3]

    expect(english.kind === 'transport' ? english.title : '').toBe(
      'Electric transport from 1,500 CZK',
    )
    expect(czech.kind === 'transport' ? czech.title : '').toBe('Elektrovozidla od 1 500 CZK')
  })
})

describe('навигация', () => {
  it('ведёт на единую сцену транспорта', () => {
    expect(navTargets(scenes)).toEqual([
      { key: 'home', label: 'Главная', index: 0 },
      { key: 'transport', label: 'Транспорт', index: 3 },
    ])
    expect(activeNavKey(scenes, 3)).toBe('transport')
  })

  it('сохраняет единый порядок при смене языка', () => {
    expect(composeScenes('en').map((scene) => scene.kind)).toEqual(scenes.map((scene) => scene.kind))
  })
})
