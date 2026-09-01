import type { Bike, BikeScene, GearScene, IntroScene, Scene } from '@/features/landing/scene.types'
import { localePath } from '@/i18n/locales'
import type { Locale } from '@/i18n/locales'
import { bikes, getBikes } from './bikes'

type IntroVisual = Pick<IntroScene, 'id' | 'background' | 'align'>
type IntroCopy = Pick<IntroScene, 'eyebrow' | 'title' | 'body'> & { ctaLabel?: string }
type GearCopy = Pick<GearScene, 'eyebrow' | 'title' | 'price' | 'badge' | 'backLabel'>

const introVisuals: IntroVisual[] = [
  {
    id: 'intro-offer',
    background: { src: '/scenes/intro-1.png', focusMobile: '52%', focusDesktop: '70%' },
    align: 'top',
  },
  {
    id: 'intro-paperwork',
    background: { src: '/scenes/intro-2.png', focusMobile: '38%', focusDesktop: '45%' },
    align: 'spread',
  },
  {
    id: 'intro-bundle',
    background: { src: '/scenes/intro-3.png', focusMobile: '42%', focusDesktop: '60%' },
    align: 'spread',
  },
]

const introCopy: Record<Locale, IntroCopy[]> = {
  ru: [
    {
      eyebrow: 'BOLT FOOD · CZ',
      title: 'Работай курьером Bolt Food в Чехии',
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
      ctaLabel: 'Оставить заявку',
    },
    {
      eyebrow: 'БЕЗ БЮРОКРАТИИ',
      title: 'Тебе не нужно ничего оформлять самому',
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
      eyebrow: 'ВСЁ В ОДНОМ МЕСТЕ',
      title: 'Подключение, транспорт и термо-сумка',
      body: {
        kind: 'paragraphs',
        items: [
          [
            'Велосипед или электровелосипед в прокат и сумка — сразу, одной заявкой. Работаем по всей Чехии.',
          ],
        ],
      },
    },
  ],
  en: [
    {
      eyebrow: 'BOLT FOOD · CZ',
      title: 'Work as a Bolt Food courier in Czechia',
      body: {
        kind: 'bullets',
        items: [
          {
            marker: '—',
            markerKind: 'dash',
            text: ['You do not need your own vehicle: rent one from us or work without one'],
          },
          {
            marker: '—',
            markerKind: 'dash',
            text: ['Fleet commission — only ', { em: '10%' }],
          },
          {
            marker: '—',
            markerKind: 'dash',
            text: ['Thermal delivery bag — ', { em: 'from 350 CZK' }],
          },
        ],
      },
      ctaLabel: 'Apply now',
    },
    {
      eyebrow: 'NO PAPERWORK',
      title: 'You do not have to arrange anything yourself',
      body: {
        kind: 'bullets',
        items: [
          { marker: '01', markerKind: 'pixel', text: ['Fill in the application'] },
          { marker: '02', markerKind: 'pixel', text: ['We handle the paperwork'] },
          { marker: '03', markerKind: 'pixel', text: ['You start delivering'] },
        ],
      },
    },
    {
      eyebrow: 'EVERYTHING IN ONE PLACE',
      title: 'Onboarding, transport and a thermal bag',
      body: {
        kind: 'paragraphs',
        items: [
          [
            'Rent a bicycle or e-bike and get a bag with one application. Available across Czechia.',
          ],
        ],
      },
    },
  ],
  cs: [
    {
      eyebrow: 'BOLT FOOD · CZ',
      title: 'Pracuj jako kurýr Bolt Food v Česku',
      body: {
        kind: 'bullets',
        items: [
          {
            marker: '—',
            markerKind: 'dash',
            text: ['Vlastní dopravní prostředek není nutný: půjč si ho od nás nebo pracuj bez něj'],
          },
          {
            marker: '—',
            markerKind: 'dash',
            text: ['Provize flotily — pouze ', { em: '10 %' }],
          },
          {
            marker: '—',
            markerKind: 'dash',
            text: ['Termotaška — ', { em: 'od 350 CZK' }],
          },
        ],
      },
      ctaLabel: 'Podat žádost',
    },
    {
      eyebrow: 'BEZ PAPÍROVÁNÍ',
      title: 'Nemusíš nic vyřizovat sám',
      body: {
        kind: 'bullets',
        items: [
          { marker: '01', markerKind: 'pixel', text: ['Vyplníš žádost'] },
          { marker: '02', markerKind: 'pixel', text: ['Všechno vyřídíme'] },
          { marker: '03', markerKind: 'pixel', text: ['Začneš rozvážet'] },
        ],
      },
    },
    {
      eyebrow: 'VŠE NA JEDNOM MÍSTĚ',
      title: 'Registrace, doprava a termotaška',
      body: {
        kind: 'paragraphs',
        items: [
          [
            'Půjč si kolo nebo elektrokolo a získej tašku v jedné žádosti. Působíme po celém Česku.',
          ],
        ],
      },
    },
  ],
}

const gearVisual = {
  kind: 'gear' as const,
  id: 'gear-bag',
  image: { src: '/gear/courier-bag.png', focus: '62%' },
}

const gearCopy: Record<Locale, GearCopy> = {
  ru: {
    eyebrow: 'ЭКИПИРОВКА',
    title: 'Термосумка‑рюкзак',
    price: '750 CZK',
    badge: 'можно в счёт зарплаты',
    backLabel: '↑ Назад к велосипеду',
  },
  en: {
    eyebrow: 'EQUIPMENT',
    title: 'Thermal delivery backpack',
    price: '750 CZK',
    badge: 'can be deducted from your pay',
    backLabel: '↑ Back to the bike',
  },
  cs: {
    eyebrow: 'VYBAVENÍ',
    title: 'Termobatoh',
    price: '750 CZK',
    badge: 'lze odečíst ze mzdy',
    backLabel: '↑ Zpět ke kolu',
  },
}

function localizedIntroScenes(locale: Locale): IntroScene[] {
  return introVisuals.map((visual, index) => {
    const { ctaLabel, ...copy } = introCopy[locale][index]
    return {
      kind: 'intro',
      ...visual,
      ...copy,
      cta: ctaLabel ? { label: ctaLabel, href: localePath(locale, 'apply') } : undefined,
    }
  })
}

function localizedGearScene(locale: Locale): GearScene {
  return { ...gearVisual, ...gearCopy[locale] }
}

/** Строит сцену велосипеда из записи каталога. */
export function toBikeScene(bike: Bike): BikeScene {
  return { kind: 'bike', id: `bike-${bike.slug}`, bike }
}

/** Собирает порядок сцен из локализованного контента и списка велосипедов. */
export function composeScenes(list: Bike[], locale: Locale = 'ru'): Scene[] {
  return [
    ...localizedIntroScenes(locale),
    ...list.map(toBikeScene),
    localizedGearScene(locale),
  ]
}

/** Готовит полный массив сцен выбранного языка. */
export function getScenes(locale: Locale): Scene[] {
  return composeScenes(getBikes(locale), locale)
}

/** Русский порядок оставлен экспортом по умолчанию для существующих потребителей. */
export const scenes: Scene[] = composeScenes(bikes)
