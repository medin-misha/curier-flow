import Link from 'next/link'
import { getMessages } from '@/i18n/messages'
import { localePath, locales } from '@/i18n/locales'
import type { Locale, SiteRoute } from '@/i18n/locales'
import styles from './LanguageSwitcher.module.css'

const shortNames: Record<Locale, string> = { ru: 'RU', en: 'EN', cs: 'CZ' }

/** Переключатель языка с отдельным индексируемым URL для каждой версии. */
export function LanguageSwitcher({ locale, route }: { locale: Locale; route: SiteRoute }) {
  const copy = getMessages(locale).language

  return (
    <nav className={styles.root} aria-label={copy.label}>
      {locales.map((target) => (
        <Link
          key={target}
          href={localePath(target, route)}
          hrefLang={target}
          lang={target}
          title={copy.names[target]}
          aria-current={target === locale ? 'page' : undefined}
          className={styles.link}
        >
          {shortNames[target]}
        </Link>
      ))}
    </nav>
  )
}
