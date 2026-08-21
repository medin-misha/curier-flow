import type { Bike, BikeScene, GearScene, IntroScene, Scene } from '@/features/landing/scene.types'
import { bikes } from './bikes'

const introScenes: IntroScene[] = [
  {
    kind: 'intro',
    id: 'intro-offer',
    eyebrow: 'BOLT FOOD · CZ',
    title: 'Работай курьером Bolt Food в Чехии',
    background: { src: '/scenes/intro-1.png', focusMobile: '52%', focusDesktop: '70%' },
    align: 'top',
    body: {
      kind: 'bullets',
      items: [
        {
          marker: '—',
          markerKind: 'dash',
          text: ['Свой транспорт иметь необязательно: можно взять у нас или работать без него'],
        },
        {
          marker: '—',
          markerKind: 'dash',
          text: ['Комиссия флотилии — всего ', { em: '10%' }],
        },
        {
          marker: '—',
          markerKind: 'dash',
          text: ['Термо-сумка — ', { em: 'от 350 CZK' }],
        },
      ],
    },
    cta: { label: 'Оставить заявку', href: '/apply' },
  },
  {
    kind: 'intro',
    id: 'intro-paperwork',
    eyebrow: 'БЕЗ БЮРОКРАТИИ',
    title: 'Тебе не нужно ничего оформлять самому',
    background: { src: '/scenes/intro-2.png', focusMobile: '38%', focusDesktop: '45%' },
    body: {
      kind: 'bullets',
      items: [
        { marker: '01', markerKind: 'pixel', text: ['Заполняешь анкету'] },
        { marker: '02', markerKind: 'pixel', text: ['Мы всё оформляем'] },
        { marker: '03', markerKind: 'pixel', text: ['Ты выходишь на линию'] },
      ],
    },
  },
  {
    kind: 'intro',
    id: 'intro-bundle',
    eyebrow: 'ВСЁ В ОДНОМ МЕСТЕ',
    title: 'Подключение, транспорт и термо-сумка',
    background: { src: '/scenes/intro-3.png', focusMobile: '42%', focusDesktop: '60%' },
    body: {
      kind: 'paragraphs',
      items: [
        [
          'Велосипед или электровелосипед в прокат и сумка — сразу, одной заявкой. Работаем по всей Чехии.',
        ],
      ],
    },
  },
]

const gearScene: GearScene = {
  kind: 'gear',
  id: 'gear-bag',
  eyebrow: 'ЭКИПИРОВКА',
  title: 'Термосумка‑рюкзак',
  image: { src: '/gear/courier-bag.png', focus: '62%' },
  price: '750 CZK',
  badge: 'можно в счёт зарплаты',
  backLabel: '↑ Назад к велосипеду',
}

/**
 * Строит сцену велосипеда из записи каталога.
 *
 * Принимает: `bike` — запись из `bikes.ts`.
 * Возвращает: сцену вида `bike` для массива `scenes`.
 * Экспортируется для теста и для будущей сборки сцен из другого источника.
 */
export function toBikeScene(bike: Bike): BikeScene {
  return { kind: 'bike', id: `bike-${bike.slug}`, bike }
}

/**
 * Собирает порядок сцен: сначала вводные, затем все велосипеды, в конце экипировка.
 *
 * Вынесено функцией, чтобы тест мог прогнать через ту же сборку другой список
 * велосипедов, а не воспроизводить её у себя.
 */
export function composeScenes(list: Bike[]): Scene[] {
  return [...introScenes, ...list.map(toBikeScene), gearScene]
}

/**
 * Порядок сцен лендинга.
 *
 * Новый велосипед добавляется в `bikes.ts` — здесь ничего править не нужно.
 * Номер в подписи сцены («01 / …») считается из позиции, поэтому нумерация
 * пересобирается сама.
 */
export const scenes: Scene[] = composeScenes(bikes)
