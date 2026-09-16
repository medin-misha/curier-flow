import { describe, expect, it } from 'vitest'
import { sceneIndexFromScroll } from './sceneScroll'

describe('sceneIndexFromScroll', () => {
  it('в начале страницы отдаёт первую сцену', () => {
    expect(sceneIndexFromScroll(0, 800, 5)).toBe(0)
  })

  it('переключает сцену на середине экрана', () => {
    expect(sceneIndexFromScroll(320, 800, 5)).toBe(0)
    expect(sceneIndexFromScroll(480, 800, 5)).toBe(1)
  })

  it('попадает точно в сцену на кратной высоте', () => {
    expect(sceneIndexFromScroll(2400, 800, 5)).toBe(3)
  })

  it('ограничивает индекс последней сценой', () => {
    expect(sceneIndexFromScroll(99_999, 800, 5)).toBe(4)
  })

  it('ограничивает индекс нулём при отрицательном скролле', () => {
    expect(sceneIndexFromScroll(-200, 800, 5)).toBe(0)
  })

  it('не делит на ноль при нулевой высоте окна', () => {
    expect(sceneIndexFromScroll(500, 0, 5)).toBe(0)
  })

  it('отдаёт ноль при пустом списке сцен', () => {
    expect(sceneIndexFromScroll(500, 800, 0)).toBe(0)
  })
})
