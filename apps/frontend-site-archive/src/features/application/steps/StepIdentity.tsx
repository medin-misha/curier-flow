import { PixelChip } from '@/components/PixelChip'
import { getMessages } from '@/i18n/messages'
import type { Locale } from '@/i18n/locales'
import { cities } from '@/content/application'
import { Field, TextInput } from '../Field'
import { ageHint } from '../hints'
import type { ApplyWizard } from '../useApplyWizard'
import styles from './Step.module.css'

/** Шаг 1: имя, дата рождения, город и адрес. */
export function StepIdentity({
  wizard,
  locale = 'ru',
}: {
  wizard: ApplyWizard
  locale?: Locale
}) {
  const { form, setField, now } = wizard
  const copy = getMessages(locale).application.identity

  return (
    <section className={styles.section}>
      <div className={styles.head}>
        <h1 className={styles.title}>{copy.title}</h1>
        <p className={styles.lead}>{copy.lead}</p>
      </div>

      <p className={styles.paymentInfo}>{copy.paymentInfo}</p>

      <div className={styles.fields}>
        <Field label={copy.fullName}>
          <TextInput
            value={form.fullName}
            onChange={(event) => setField('fullName', event.target.value)}
            placeholder="Ivan Ivanov"
            autoComplete="name"
            maxLength={255}
          />
        </Field>

        <Field label={copy.birthDate} hint={ageHint(form.birthDate, now(), locale)}>
          <TextInput
            type="date"
            value={form.birthDate}
            onChange={(event) => setField('birthDate', event.target.value)}
          />
        </Field>

        <div className={styles.group}>
          <span className={styles.groupTitle}>{copy.city}</span>
          <div className={styles.chips}>
            {cities.map((city) => (
              <PixelChip
                key={city}
                selected={form.city === city}
                onClick={() => setField('city', city)}
              >
                {city}
              </PixelChip>
            ))}
          </div>
          <TextInput
            value={form.city}
            onChange={(event) => setField('city', event.target.value)}
            placeholder={copy.cityPlaceholder}
            aria-label={copy.city}
            maxLength={128}
          />
        </div>

        <Field label={copy.address}>
          <TextInput
            value={form.address}
            onChange={(event) => setField('address', event.target.value)}
            placeholder={copy.addressPlaceholder}
            autoComplete="street-address"
          />
        </Field>
      </div>
    </section>
  )
}
