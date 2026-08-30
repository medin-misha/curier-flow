import { PixelLink } from '@/components/PixelButton'
import type { Messenger } from './form.types'
import styles from './SuccessScreen.module.css'

/** Экран после успешной отправки или естественно идемпотентного повтора. */
export function SuccessScreen({ messenger, existing }: { messenger: Messenger; existing: boolean }) {
  return (
    <section className={styles.root}>
      <div className={styles.mark}>OK!</div>
      <h1 className={styles.title}>
        {existing ? 'Заявка уже зарегистрирована' : 'Заявка отправлена'}
      </h1>
      <p className={styles.lead}>
        {existing
          ? 'Мы уже получили твои данные и напишем тебе в '
          : 'Проверим документы и напишем тебе в '}
        <span className={styles.messenger}>{messenger}</span> в течение рабочего дня. Обычно это
        занимает пару часов.
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
