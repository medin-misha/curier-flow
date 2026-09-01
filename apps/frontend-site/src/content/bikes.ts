import type { Bike } from '@/features/landing/scene.types'
import type { Locale } from '@/i18n/locales'

type BikeCopy = Pick<Bike, 'name' | 'specs' | 'description' | 'price'>
type BikeCatalogEntry = Pick<Bike, 'slug' | 'media'> & { copy: Record<Locale, BikeCopy> }

/** Каталог: медиа задаются один раз, пользовательский текст — для каждого языка. */
export const bikeCatalog: BikeCatalogEntry[] = [
  {
    slug: 'urban-e1',
    media: {
      poster: '/bikes/urban-e1/poster.png',
      video: '/bikes/urban-e1/loop.mp4',
      focus: '58%',
    },
    copy: {
      ru: {
        name: 'MFS Urban E1',
        specs: [
          { label: 'АКБ', value: '48V · 20Ah', note: 'зарядка 4–5 часов' },
          { label: 'ЗАПАС ХОДА', value: 'до 65 км', note: 'на одном заряде' },
        ],
        description: [
          'Электровелосипед-фэтбайк для города. Выдаём заряженным, с креплением под термо-сумку.',
        ],
        price: { amount: 'от 1750 CZK', period: 'в неделю' },
      },
      en: {
        name: 'MFS Urban E1',
        specs: [
          { label: 'BATTERY', value: '48V · 20Ah', note: '4–5 hour charge' },
          { label: 'RANGE', value: 'up to 65 km', note: 'on one charge' },
        ],
        description: [
          'A fat-tire e-bike for city deliveries. Supplied charged and fitted with a thermal bag mount.',
        ],
        price: { amount: 'from 1,750 CZK', period: 'per week' },
      },
      cs: {
        name: 'MFS Urban E1',
        specs: [
          { label: 'BATERIE', value: '48V · 20Ah', note: 'nabíjení 4–5 hodin' },
          { label: 'DOJEZD', value: 'až 65 km', note: 'na jedno nabití' },
        ],
        description: [
          'Městské elektrokolo s širokými plášti. Předáváme ho nabité a s držákem na termotašku.',
        ],
        price: { amount: 'od 1 750 CZK', period: 'za týden' },
      },
    },
  },
]

/** Готовая UI-модель каталога для выбранного языка. */
export function getBikes(locale: Locale): Bike[] {
  return bikeCatalog.map(({ slug, media, copy }) => ({ slug, media, ...copy[locale] }))
}

/** Русский каталог оставлен экспортом по умолчанию для существующих потребителей. */
export const bikes: Bike[] = getBikes('ru')
