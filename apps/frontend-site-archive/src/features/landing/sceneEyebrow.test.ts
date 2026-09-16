import { describe, expect, it } from 'vitest'
import { sceneEyebrow } from './sceneEyebrow'

describe('sceneEyebrow', () => {
  it('нумерует с единицы и дополняет нулём', () => {
    expect(sceneEyebrow(0, 'BOLT FOOD · CZ')).toBe('01 / BOLT FOOD · CZ')
    expect(sceneEyebrow(4, 'ЭКИПИРОВКА')).toBe('05 / ЭКИПИРОВКА')
  })

  it('не теряет разряд после девятой сцены', () => {
    expect(sceneEyebrow(11, 'ЭКИПИРОВКА')).toBe('12 / ЭКИПИРОВКА')
  })

  it('перестаёт дополнять нулём ровно на десятой сцене', () => {
    expect(sceneEyebrow(8, 'ЭКИПИРОВКА')).toBe('09 / ЭКИПИРОВКА')
    expect(sceneEyebrow(9, 'ЭКИПИРОВКА')).toBe('10 / ЭКИПИРОВКА')
  })
})
