import { getMessages } from '@/i18n/messages'
import type { Locale } from '@/i18n/locales'
import type { Scene } from './scene.types'

export type NavKey = 'home' | 'transport' | 'gear'

export interface NavTarget {
  key: NavKey
  label: string
  index: number
}

/**
 * Пункты меню и сцены, к которым они ведут.
 *
 * Индексы считаются из массива сцен, поэтому новый велосипед сдвигает
 * цель «Сумки» сам, без правок в шапке.
 */
export function navTargets(scenes: Scene[], locale: Locale = 'ru'): NavTarget[] {
  const labels = getMessages(locale).landing.nav
  const targets: NavTarget[] = [{ key: 'home', label: labels.home, index: 0 }]

  const transport = scenes.findIndex((scene) => scene.kind === 'bike')
  if (transport >= 0) {
    targets.push({ key: 'transport', label: labels.transport, index: transport })
  }

  const gear = scenes.findIndex((scene) => scene.kind === 'gear')
  if (gear >= 0) targets.push({ key: 'gear', label: labels.gear, index: gear })

  return targets
}

/** Пункт меню, соответствующий активной сцене. */
export function activeNavKey(scenes: Scene[], activeIndex: number): NavKey {
  const kind = scenes[activeIndex]?.kind
  if (kind === 'bike') return 'transport'
  if (kind === 'gear') return 'gear'
  return 'home'
}

/** Индекс последнего велосипеда; -1, если велосипедов нет. */
export function lastBikeIndex(scenes: Scene[]): number {
  return scenes.findLastIndex((scene) => scene.kind === 'bike')
}

/** Имя велосипеда активной сцены для вывода в шапке. */
export function activeBikeName(scenes: Scene[], activeIndex: number): string | null {
  const scene = scenes[activeIndex]
  return scene?.kind === 'bike' ? scene.bike.name : null
}
