/**
 * Отображение позиции скролла в индекс активной сцены.
 *
 * Одна сцена занимает высоту окна, поэтому индекс — округлённое частное.
 * Округление, а не пол: сцена считается активной, когда занимает
 * бо́льшую часть экрана.
 */
export function sceneIndexFromScroll(
  scrollY: number,
  viewportHeight: number,
  sceneCount: number,
): number {
  if (sceneCount <= 0 || viewportHeight <= 0) return 0

  const raw = Math.round(scrollY / viewportHeight)
  return Math.min(Math.max(raw, 0), sceneCount - 1)
}

/** Плавный скролл к началу сцены. */
export function scrollToScene(index: number): void {
  window.scrollTo({ top: window.innerHeight * index, behavior: 'smooth' })
}
