import { getMessages } from '@/i18n/messages'
import type { Locale } from '@/i18n/locales'
import styles from './ScrollHint.module.css'

/** Подсказка скролла. Гаснет при переходе к контактам. */
export function ScrollHint({ hidden, locale = 'ru' }: { hidden: boolean; locale?: Locale }) {
  return (
    <div className={styles.root} data-hidden={hidden} aria-hidden="true">
      {getMessages(locale).landing.scrollHint}
    </div>
  )
}
