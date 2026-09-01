import { Fragment } from 'react'
import { company } from '@/content/company'
import { getMessages } from '@/i18n/messages'
import type { Locale } from '@/i18n/locales'
import styles from './SiteFooter.module.css'

/**
 * Футер: реквизиты и контакты.
 *
 * Подпись приходит готовой строкой: футер не знает про сцены, номер за него
 * считает тот, кто владеет их массивом.
 */
export function SiteFooter({ eyebrow, locale = 'ru' }: { eyebrow: string; locale?: Locale }) {
  const copy = getMessages(locale).landing.footer

  return (
    <footer className={styles.root}>
      <div className={styles.top}>
        <img src="/logo.svg" alt="May Fleet Solutions" className={styles.logo} />
        <span className={styles.eyebrow}>{eyebrow}</span>
      </div>

      <div className={styles.columns}>
        <div className={styles.column}>
          <span className={styles.columnTitle}>{copy.details}</span>
          <span className={styles.legalName}>{company.legalName}</span>
          <span className={styles.address}>
            {company.addressLines.map((line, index) => (
              <Fragment key={line}>
                {index > 0 ? <br /> : null}
                {line}
              </Fragment>
            ))}
          </span>
          <span className={styles.icoRow}>
            <span className={styles.icoLabel}>IČO</span>
            <span className={styles.icoValue}>{company.ico}</span>
          </span>
          <span className={styles.registration}>{company.registration}</span>
        </div>

        <div className={styles.column}>
          <span className={styles.columnTitle}>{copy.contact}</span>
          <a href={company.phone.href} className={styles.phone}>
            {company.phone.display}
          </a>
          <a href={`mailto:${company.email}`} className={styles.email}>
            {company.email}
          </a>
          <a href={company.privacyPolicy.href} className={styles.policy}>
            {copy.privacy} <span className={styles.arrow}>→</span>
          </a>
        </div>
      </div>

      <div className={styles.bottom}>
        <span className={styles.copyright}>{company.copyright}</span>
        <span className={styles.city}>{company.city}</span>
      </div>
    </footer>
  )
}
