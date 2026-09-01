import { getCountryOptions } from '@/content/application'
import { getMessages } from '@/i18n/messages'
import type { Locale } from '@/i18n/locales'
import { Field, SelectInput, TextInput } from '../Field'
import { FileField } from '../FileField'
import type { ApplyWizard } from '../useApplyWizard'
import styles from './Step.module.css'

/** Шаг 3: банковский счёт, гражданство и сканы документов. */
export function StepDocuments({
  wizard,
  locale = 'ru',
}: {
  wizard: ApplyWizard
  locale?: Locale
}) {
  const { form, files, setField, setFile } = wizard
  const copy = getMessages(locale).application.documents
  const countries = getCountryOptions(locale)

  return (
    <section className={styles.section}>
      <div className={styles.head}>
        <h1 className={styles.title}>{copy.title}</h1>
        <p className={styles.lead}>{copy.lead}</p>
      </div>

      <div className={styles.fields}>
        <Field label={copy.bankAccount} hint={copy.bankHint}>
          <TextInput
            value={form.bankAccount}
            onChange={(event) => setField('bankAccount', event.target.value)}
            placeholder="CZ00 0000 0000 0000 0000 0000"
            maxLength={64}
          />
        </Field>

        <Field label={copy.citizenship}>
          <SelectInput
            value={form.citizenship}
            onChange={(event) => setField('citizenship', event.target.value)}
          >
            <option value="">{copy.countryPlaceholder}</option>
            {countries.map((country) => (
              <option key={country.value} value={country.value}>
                {country.label}
              </option>
            ))}
          </SelectInput>
        </Field>

        <div className={styles.group}>
          <span className={styles.groupTitle}>{copy.required}</span>
          <FileField
            title={copy.passport}
            order="1"
            file={files.passport}
            onSelect={(file) => setFile('passport', file)}
            locale={locale}
          />
          <FileField
            title={copy.visa}
            order="2"
            file={files.visa}
            onSelect={(file) => setFile('visa', file)}
            locale={locale}
          />
          <span className={styles.note}>{copy.fileHint}</span>
        </div>
      </div>
    </section>
  )
}
