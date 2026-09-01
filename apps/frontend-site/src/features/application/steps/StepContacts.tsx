import { PixelChip } from '@/components/PixelChip'
import { getMessages } from '@/i18n/messages'
import type { Locale } from '@/i18n/locales'
import { Field, TextInput } from '../Field'
import { messengerHint, messengerPlaceholder, phoneHint } from '../hints'
import type { Messenger } from '../form.types'
import type { ApplyWizard } from '../useApplyWizard'
import styles from './Step.module.css'

const MESSENGERS: Messenger[] = ['WhatsApp', 'Telegram']

/** Шаг 2: телефон, почта и мессенджер. */
export function StepContacts({
  wizard,
  locale = 'ru',
}: {
  wizard: ApplyWizard
  locale?: Locale
}) {
  const { form, setField } = wizard
  const copy = getMessages(locale).application.contacts

  return (
    <section className={styles.section}>
      <div className={styles.head}>
        <h1 className={styles.title}>{copy.title}</h1>
        <p className={styles.lead}>{copy.lead}</p>
      </div>

      <div className={styles.fields}>
        <div className={styles.group}>
          <span className={styles.groupTitle}>{copy.phone}</span>
          <div className={styles.phoneRow}>
            <span className={styles.phonePrefix}>+420</span>
            <input
              className={styles.phoneInput}
              inputMode="tel"
              value={form.phone}
              onChange={(event) => setField('phone', event.target.value)}
              placeholder="777 123 456"
              autoComplete="tel"
              aria-label={copy.phone}
            />
          </div>
          <span className={styles.note}>{phoneHint(form.phone, locale)}</span>
        </div>

        <Field label={copy.email}>
          <div className={styles.emailRow}>
            <TextInput
              inputMode="email"
              value={form.email}
              onChange={(event) => setField('email', event.target.value)}
              placeholder="ivan@email.com"
              autoComplete="email"
              maxLength={320}
            />
            {form.email.trim() && !form.email.includes('@') ? (
              <button
                className={styles.emailSuggestion}
                type="button"
                onClick={() => setField('email', `${form.email.trim()}@gmail.com`)}
                aria-label={copy.gmailAria}
              >
                @gmail.com
              </button>
            ) : null}
          </div>
        </Field>

        <div className={styles.panel}>
          <span className={styles.groupTitle}>{copy.messenger}</span>
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
            aria-label={copy.messengerContact(form.messenger)}
            maxLength={255}
          />
          <span className={styles.note}>{messengerHint(form.messenger, locale)}</span>
        </div>
      </div>
    </section>
  )
}
