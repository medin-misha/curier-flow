import { PixelLink } from '@/components/PixelButton'
import type { Messenger } from './form.types'
import styles from './SuccessScreen.module.css'

/** Экран после успешной отправки заявки. */
export function SuccessScreen({ messenger }: { messenger: Messenger }) {
  return (
    <section className={styles.root}>
      <div className={styles.mark}>OK!</div>
      <h1 className={styles.title}>Заявка отправлена</h1>
      <p className={styles.lead}>
        Проверим документы и напишем тебе в <span className={styles.messenger}>{messenger}</span> в
        течение рабочего дня. Обычно это занимает пару часов.
      </p>

      <div className={styles.panel}>
        <span className={styles.panelTitle}>Что дальше</span>
        <span className={styles.panelText}>
          Держи телефон под рукой — попросим подтвердить пару данных и договоримся о выдаче сумки и
          транспорта.
        </span>
      </div>

      <PixelLink href="/" variant="primary" size="md" className={styles.home}>
        На главную
      </PixelLink>
    </section>
  )
}
