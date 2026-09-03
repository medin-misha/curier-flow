import type { IntroScene, Scene, TransportScene } from '@/features/landing/scene.types'
import { localePath } from '@/i18n/locales'
import type { Locale } from '@/i18n/locales'

type IntroVisual = Pick<IntroScene, 'id' | 'background' | 'align'>
type IntroCopy = Pick<IntroScene, 'eyebrow' | 'title' | 'body'> & { ctaLabel?: string }
type TransportCopy = Pick<TransportScene, 'eyebrow' | 'title' | 'description'>
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
            text: ['Маленькая комиссия'],
          },
          {
            marker: '—',
            markerKind: 'dash',
            text: ['Мы можем предоставить термосумку'],
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
            text: ['Small commission'],
          },
          {
            marker: '—',
            markerKind: 'dash',
            text: ['We can provide a thermal delivery bag'],
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
            text: ['Malá provize'],
          },
          {
            marker: '—',
            markerKind: 'dash',
            text: ['Můžeme poskytnout termotašku'],
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

const transportVisual: Pick<TransportScene, 'id' | 'media'> = {
  id: 'transport',
  media: { poster: '/transport/poster.png', video: '/transport/loop.mp4', focus: '58%' },
}

const transportCopy: Record<Locale, TransportCopy> = {
  ru: {
    eyebrow: 'ЭЛЕКТРОТРАНСПОРТ',
    title: 'Электро-транспорт от 1500 CZK',
    description: ['Электротранспорт для работы курьером — выбирай подходящий вариант.'],
  },
  en: {
    eyebrow: 'ELECTRIC TRANSPORT',
    title: 'Electric transport from 1,500 CZK',
    description: ['Electric transport for courier work — choose the option that suits you.'],
  },
  cs: {
    eyebrow: 'ELEKTRODOPRAVA',
    title: 'Elektrovozidla od 1 500 CZK',
    description: ['Elektrodoprava pro práci kurýra — vyber si variantu, která ti vyhovuje.'],
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

function localizedTransportScene(locale: Locale): TransportScene {
  return { kind: 'transport', ...transportVisual, ...transportCopy[locale] }
}

/** Собирает единый порядок сцен лендинга. */
export function composeScenes(locale: Locale = 'ru'): Scene[] {
  return [...localizedIntroScenes(locale), localizedTransportScene(locale)]
}

/** Готовит полный массив сцен выбранного языка. */
export function getScenes(locale: Locale): Scene[] {
  return composeScenes(locale)
}

/** Русский порядок оставлен экспортом по умолчанию для существующих потребителей. */
export const scenes: Scene[] = composeScenes()
