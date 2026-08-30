import { countries } from '@/content/application'
import { Field, SelectInput, TextInput } from '../Field'
import { FileField } from '../FileField'
import type { ApplyWizard } from '../useApplyWizard'
import styles from './Step.module.css'

/** Шаг 3: банковский счёт, гражданство и сканы документов. */
export function StepDocuments({ wizard }: { wizard: ApplyWizard }) {
  const { form, files, setField, setFile } = wizard

  return (
    <section className={styles.section}>
      <div className={styles.head}>
        <h1 className={styles.title}>Документы и счёт</h1>
        <p className={styles.lead}>
          Паспорт и визу или ВНЖ запрашиваем только для оформления во флоте. Счёт — чтобы платить
          тебе за смены.
        </p>
      </div>

      <div className={styles.fields}>
        <Field label="Счёт в чешском банке" hint="IBAN или номер счёта с кодом банка">
          <TextInput
            value={form.bankAccount}
            onChange={(event) => setField('bankAccount', event.target.value)}
            placeholder="CZ00 0000 0000 0000 0000 0000"
            maxLength={64}
          />
        </Field>

        <Field label="Гражданство">
          <SelectInput
            value={form.citizenship}
            onChange={(event) => setField('citizenship', event.target.value)}
          >
            <option value="">Выбери страну</option>
            {countries.map((country) => (
              <option key={country} value={country}>
                {country}
              </option>
            ))}
          </SelectInput>
        </Field>

        <div className={styles.group}>
          <span className={styles.groupTitle}>Документы — обязательно</span>
          <FileField
            title="Скан паспорта"
            order="1"
            file={files.passport}
            onSelect={(file) => setFile('passport', file)}
          />
          <FileField
            title="Скан визы / ВНЖ"
            order="2"
            file={files.visa}
            onSelect={(file) => setFile('visa', file)}
          />
          <span className={styles.note}>
            Фото или PDF, до 10 МБ. Главное — чтобы читались все данные.
          </span>
        </div>
      </div>
    </section>
  )
}
