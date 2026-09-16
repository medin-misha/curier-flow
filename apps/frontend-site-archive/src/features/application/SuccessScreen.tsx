import { LanguageSwitcher } from '@/components/LanguageSwitcher'
import { PixelLink } from '@/components/PixelButton'
import { getMessages } from '@/i18n/messages'
import { localePath } from '@/i18n/locales'
import type { Locale } from '@/i18n/locales'
import type { Messenger } from './form.types'
import styles from './SuccessScreen.module.css'

/** Экран после успешной отправки или естественно идемпотентного повтора. */
export function SuccessScreen({
  messenger,
  existing,
  locale = 'ru',
}: {
  messenger: Messenger
  existing: boolean
  locale?: Locale
}) {
  const copy = getMessages(locale).application.success

  return (
    <section className={styles.root}>
      <div className={styles.languages}>
        <LanguageSwitcher locale={locale} route="apply" />
      </div>
      <div className={styles.mark}>OK!</div>
      <h1 className={styles.title}>{existing ? copy.existingTitle : copy.sentTitle}</h1>
      <p className={styles.lead}>
        {existing ? copy.existingBefore : copy.sentBefore}
        <span className={styles.messenger}>{messenger}</span>
        {copy.after}
      </p>

      <div className={styles.panel}>
        <span className={styles.panelTitle}>{copy.nextTitle}</span>
        <span className={styles.panelText}>{copy.nextText}</span>
      </div>

      <PixelLink
        href={localePath(locale, 'landing')}
        variant="primary"
        size="md"
        className={styles.home}
      >
        {copy.home}
      </PixelLink>
    </section>
  )
}
