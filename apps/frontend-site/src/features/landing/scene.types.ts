/**
 * Типы сцен лендинга.
 *
 * Лендинг — упорядоченный массив сцен. Вид сцены задан размеченным
 * объединением, чтобы компилятор требовал поля, обязательные именно
 * для этого вида: у велосипеда — характеристики и цену, у вводной
 * сцены — фон и текстовый блок.
 */

/** Фрагмент текста. Объект означает выделенный фрагмент. */
export type TextSegment = string | { em: string }

export interface Bullet {
  /** Символ или номер слева от строки. */
  marker: string
  /** `dash` — акцентный символ, `pixel` — номер пиксельным шрифтом. */
  markerKind: 'dash' | 'pixel'
  text: TextSegment[]
}

export type SceneBody =
  | { kind: 'bullets'; items: Bullet[] }
  | { kind: 'paragraphs'; items: TextSegment[][] }

export interface Spec {
  label: string
  value: string
  note: string
}

export interface Bike {
  slug: string
  /** Выводится в шапке, пока активна сцена этого велосипеда. */
  name: string
  media: {
    poster: string
    video?: string
    /** `object-position` по горизонтали, например `58%`. */
    focus: string
  }
  /** Ровно две: левый и правый блок у краёв экрана. */
  specs: [Spec, Spec]
  description: string[]
  price: { amount: string; period: string }
}

export interface IntroScene {
  kind: 'intro'
  id: string
  /** Подпись без номера — номер считается из позиции сцены. */
  eyebrow: string
  title: string
  background: {
    src: string
    focusMobile: string
    focusDesktop: string
  }
  body: SceneBody
  /** `top` прижимает блок к верху, `spread` растягивает по высоте. */
  align?: 'top' | 'spread'
  cta?: { label: string; href: string }
}

export interface BikeScene {
  kind: 'bike'
  id: string
  eyebrow?: string
  bike: Bike
}

export interface GearScene {
  kind: 'gear'
  id: string
  eyebrow: string
  title: string
  image: { src: string; focus: string }
  price: string
  badge?: string
  backLabel: string
}

export type Scene = IntroScene | BikeScene | GearScene
