export const locales = ['ru', 'en', 'cs'] as const
export const localizedLocales = ['en', 'cs'] as const

export type Locale = (typeof locales)[number]
export type LocalizedLocale = (typeof localizedLocales)[number]
export type SiteRoute = 'landing' | 'apply'

export function isLocale(value: string): value is Locale {
  return locales.includes(value as Locale)
}

export function isLocalizedLocale(value: string): value is LocalizedLocale {
  return localizedLocales.includes(value as LocalizedLocale)
}

/** Русская версия сохраняет исходные URL, остальные языки получают префикс. */
export function localePath(locale: Locale, route: SiteRoute): string {
  const suffix = route === 'apply' ? '/apply' : ''
  return locale === 'ru' ? suffix || '/' : `/${locale}${suffix}`
}
