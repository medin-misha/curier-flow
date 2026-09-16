/**
 * Типы сцен лендинга.
 *
 * Лендинг — упорядоченный массив сцен. Вид сцены задан размеченным
 * объединением, чтобы компилятор требовал поля, обязательные именно
 * для этого вида: у транспорта — медиа, заголовок и описание, у вводной
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

export interface TransportScene {
  kind: 'transport'
  id: string
  eyebrow: string
  title: string
  media: {
    poster: string
    video?: string
    /** `object-position` по горизонтали, например `58%`. */
    focus: string
  }
  description: string[]
}

export type Scene = IntroScene | TransportScene
