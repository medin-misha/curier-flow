import { PixelChip } from '@/components/PixelChip'
import { cities } from '@/content/application'
import { Field, TextInput } from '../Field'
import { ageHint } from '../hints'
import type { ApplyWizard } from '../useApplyWizard'
import styles from './Step.module.css'

/** Шаг 1: имя, дата рождения, город и адрес. */
export function StepIdentity({ wizard }: { wizard: ApplyWizard }) {
  const { form, setField, now } = wizard

  return (
    <section className={styles.section}>
      <div className={styles.head}>
        <h1 className={styles.title}>Кто ты</h1>
        <p className={styles.lead}>Пиши как в паспорте — по этим данным оформим тебя во флоте.</p>
      </div>

      <div className={styles.fields}>
        <Field label="Имя и фамилия">
          <TextInput
            value={form.fullName}
            onChange={(event) => setField('fullName', event.target.value)}
            placeholder="Ivan Ivanov"
            autoComplete="name"
          />
        </Field>

        <Field label="Дата рождения" hint={ageHint(form.birthDate, now())}>
          <TextInput
            type="date"
            value={form.birthDate}
            onChange={(event) => setField('birthDate', event.target.value)}
          />
        </Field>

        <div className={styles.group}>
          <span className={styles.groupTitle}>Город</span>
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
            placeholder="Или впиши свой город"
            aria-label="Город"
          />
        </div>

        <Field label="Адрес проживания">
          <TextInput
            value={form.address}
            onChange={(event) => setField('address', event.target.value)}
            placeholder="Улица, дом, квартира"
            autoComplete="street-address"
          />
        </Field>
      </div>
    </section>
  )
}
