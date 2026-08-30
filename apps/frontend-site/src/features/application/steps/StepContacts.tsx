import { PixelChip } from '@/components/PixelChip'
import { Field, TextInput } from '../Field'
import { messengerHint, messengerPlaceholder, phoneHint } from '../hints'
import type { Messenger } from '../form.types'
import type { ApplyWizard } from '../useApplyWizard'
import styles from './Step.module.css'

const MESSENGERS: Messenger[] = ['WhatsApp', 'Telegram']

/** Шаг 2: телефон, почта и мессенджер. */
export function StepContacts({ wizard }: { wizard: ApplyWizard }) {
  const { form, setField } = wizard

  return (
    <section className={styles.section}>
      <div className={styles.head}>
        <h1 className={styles.title}>Как связаться</h1>
        <p className={styles.lead}>
          Чешский номер нужен для регистрации на платформе — без него аккаунт не создать.
        </p>
      </div>

      <div className={styles.fields}>
        <div className={styles.group}>
          <span className={styles.groupTitle}>Чешский номер телефона</span>
          <div className={styles.phoneRow}>
            <span className={styles.phonePrefix}>+420</span>
            <input
              className={styles.phoneInput}
              inputMode="tel"
              value={form.phone}
              onChange={(event) => setField('phone', event.target.value)}
              placeholder="777 123 456"
              autoComplete="tel"
              aria-label="Чешский номер телефона"
            />
          </div>
          <span className={styles.note}>{phoneHint(form.phone)}</span>
        </div>

        <Field label="Почта">
          <TextInput
            inputMode="email"
            value={form.email}
            onChange={(event) => setField('email', event.target.value)}
            placeholder="ivan@email.com"
            autoComplete="email"
            maxLength={320}
          />
        </Field>

        <div className={styles.panel}>
          <span className={styles.groupTitle}>Где тебе написать</span>
          <div className={styles.messengerRow}>
            {MESSENGERS.map((messenger) => (
              <PixelChip
                key={messenger}
                wide
                selected={form.messenger === messenger}
                onClick={() => setField('messenger', messenger)}
              >
                {messenger}
              </PixelChip>
            ))}
          </div>
          <TextInput
            value={form.messengerContact}
            onChange={(event) => setField('messengerContact', event.target.value)}
            placeholder={messengerPlaceholder(form.messenger)}
            aria-label={`Контакт в ${form.messenger}`}
            maxLength={255}
          />
          <span className={styles.note}>{messengerHint(form.messenger)}</span>
        </div>
      </div>
    </section>
  )
}
