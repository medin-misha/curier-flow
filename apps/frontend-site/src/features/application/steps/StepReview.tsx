import { getMessages } from '@/i18n/messages'
import type { Locale } from '@/i18n/locales'
import { reviewRows } from '../reviewRows'
import type { ApplyWizard } from '../useApplyWizard'
import styles from './Step.module.css'

/** Шаг 4: сводка введённого и согласие на обработку данных. */
export function StepReview({
  wizard,
  locale = 'ru',
}: {
  wizard: ApplyWizard
  locale?: Locale
}) {
  const { form, files, setField, goTo } = wizard
  const copy = getMessages(locale).application.review
  const rows = reviewRows(form, files, locale)

  return (
    <section className={styles.section}>
      <div className={styles.head}>
        <h1 className={styles.title}>{copy.title}</h1>
        <p className={styles.lead}>{copy.lead}</p>
      </div>

      <div className={styles.review}>
        {rows.map((row) => (
          <div key={row.label} className={styles.reviewRow}>
            <span className={styles.reviewLabel}>{row.label}</span>
            <span className={styles.reviewValueRow}>
              <span className={styles.reviewValue} data-filled={row.filled}>
                {row.value}
              </span>
              <button
                type="button"
                className={styles.reviewEdit}
                onClick={() => goTo(row.step)}
                aria-label={copy.editAria(row.label)}
              >
                {copy.edit}
              </button>
            </span>
          </div>
        ))}
      </div>

      <label className={styles.consent}>
        <input
          type="checkbox"
          className={styles.consentBox}
          checked={form.consent}
          onChange={(event) => setField('consent', event.target.checked)}
        />
        <span className={styles.consentText}>
          {copy.consentBefore}
          <a href="#">{copy.privacy}</a>
          {copy.consentAfter}
        </span>
      </label>

      <p className={styles.legal}>{copy.legal}</p>
    </section>
  )
}
