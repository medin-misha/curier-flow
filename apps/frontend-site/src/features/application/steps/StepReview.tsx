import { reviewRows } from '../reviewRows'
import type { ApplyWizard } from '../useApplyWizard'
import styles from './Step.module.css'

/** Шаг 4: сводка введённого и согласие на обработку данных. */
export function StepReview({ wizard }: { wizard: ApplyWizard }) {
  const { form, files, setField, goTo } = wizard
  const rows = reviewRows(form, files)

  return (
    <section className={styles.section}>
      <div className={styles.head}>
        <h1 className={styles.title}>Проверь и отправь</h1>
        <p className={styles.lead}>
          Последний шаг. После отправки данные уйдут только нашему флоту.
        </p>
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
                aria-label={`Изменить: ${row.label}`}
              >
                Изм.
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
          Согласен с <a href="#">политикой конфиденциальности</a> и обработкой персональных данных и
          сканов документов для оформления во флоте.
        </span>
      </label>

      <p className={styles.legal}>
        Данные передаются по защищённому соединению. Сканы храним только для оформления и удаляем
        по установленному сроку хранения.
      </p>
    </section>
  )
}
