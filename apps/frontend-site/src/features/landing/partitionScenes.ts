import type { Scene } from './scene.types'

export interface IndexedScene {
  scene: Scene
  index: number
}

/**
 * Делит сцены на два потока рендера.
 *
 * `stage` рисуется внутри sticky-вьюпорта. `overlay` — экипировка: её панель
 * выезжает поверх всей страницы и должна уходить под футер, поэтому живёт
 * отдельным слоем документа, а не внутри вьюпорта.
 *
 * Исходный индекс сохраняется: от него зависят порядок слоёв и позиция скролла.
 */
export function partitionScenes(scenes: Scene[]): {
  stage: IndexedScene[]
  overlay: IndexedScene[]
} {
  const indexed: IndexedScene[] = scenes.map((scene, index) => ({ scene, index }))

  return {
    stage: indexed.filter((entry) => entry.scene.kind !== 'gear'),
    overlay: indexed.filter((entry) => entry.scene.kind === 'gear'),
  }
}
