import { getMessages } from '@/i18n/messages'
import type { Locale } from '@/i18n/locales'
import type { Scene } from './scene.types'

export type NavKey = 'home' | 'transport'

export interface NavTarget {
  key: NavKey
  label: string
  index: number
}

/**
 * Пункты меню и сцены, к которым они ведут.
 *
 * Индексы считаются из массива сцен, чтобы меню не хранило дублирующиеся
 * позиции сцен.
 */
export function navTargets(scenes: Scene[], locale: Locale = 'ru'): NavTarget[] {
  const labels = getMessages(locale).landing.nav
  const targets: NavTarget[] = [{ key: 'home', label: labels.home, index: 0 }]

  const transport = scenes.findIndex((scene) => scene.kind === 'transport')
  if (transport >= 0) {
    targets.push({ key: 'transport', label: labels.transport, index: transport })
  }

  return targets
}

/** Пункт меню, соответствующий активной сцене. */
export function activeNavKey(scenes: Scene[], activeIndex: number): NavKey {
  const kind = scenes[activeIndex]?.kind
  if (kind === 'transport') return 'transport'
  return 'home'
}
