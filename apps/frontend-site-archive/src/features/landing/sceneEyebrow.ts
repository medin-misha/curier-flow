/**
 * Подпись сцены с порядковым номером.
 *
 * Номер берётся из позиции в массиве, а не из контента: добавление
 * велосипеда пересобирает нумерацию само.
 */
export function sceneEyebrow(index: number, label: string): string {
  return `${String(index + 1).padStart(2, '0')} / ${label}`
}
