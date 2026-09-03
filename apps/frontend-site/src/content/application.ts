import type { Locale } from '@/i18n/locales'

/** Города, вынесенные в чипы быстрого выбора. Свой город вводится вручную. */
export const cities = ['Praha', 'Brno', 'Ostrava', 'Plzeň', 'Liberec'] as const

/** Значение гражданства сохраняется в payload независимо от языка интерфейса. */
export const CZECH_CITIZENSHIP = 'Чехия'

/** Значения сохраняют текущий backend payload, подписи локализуются отдельно. */
export const countries = [
  'Украина',
  'Россия',
  'Беларусь',
  'Казахстан',
  'Узбекистан',
  'Молдова',
  'Грузия',
  'Армения',
  'Кыргызстан',
  'Таджикистан',
  'Чехия',
  'Другое',
] as const

const countryLabels: Record<Locale, readonly string[]> = {
  ru: countries,
  en: [
    'Ukraine',
    'Russia',
    'Belarus',
    'Kazakhstan',
    'Uzbekistan',
    'Moldova',
    'Georgia',
    'Armenia',
    'Kyrgyzstan',
    'Tajikistan',
    'Czechia',
    'Other',
  ],
  cs: [
    'Ukrajina',
    'Rusko',
    'Bělorusko',
    'Kazachstán',
    'Uzbekistán',
    'Moldavsko',
    'Gruzie',
    'Arménie',
    'Kyrgyzstán',
    'Tádžikistán',
    'Česko',
    'Jiné',
  ],
}

export function getCountryOptions(locale: Locale) {
  return countries.map((value, index) => ({ value, label: countryLabels[locale][index] }))
}
