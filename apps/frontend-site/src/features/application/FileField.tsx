import type { ChangeEvent } from 'react'
import { getMessages } from '@/i18n/messages'
import type { Locale } from '@/i18n/locales'
import { DOCUMENT_FILE_ACCEPT } from './validation'
import styles from './FileField.module.css'

/** Поле загрузки скана: сам инпут скрыт, кликом работает вся плашка. */
export function FileField({
  title,
  file,
  order,
  onSelect,
  locale = 'ru',
}: {
  title: string
  file: File | null
  /** Номер на значке, пока файл не выбран. */
  order: string
  onSelect: (file: File | null) => void
  locale?: Locale
}) {
  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    onSelect(event.target.files?.[0] ?? null)
  }

  return (
    <label className={styles.root}>
      <span className={styles.badge} data-filled={file !== null}>
        {file ? 'OK' : order}
      </span>
      <span className={styles.text}>
        <span className={styles.title}>{title}</span>
        <span className={styles.fileName}>
          {file?.name ?? getMessages(locale).application.fileUpload}
        </span>
      </span>
      <input
        type="file"
        accept={DOCUMENT_FILE_ACCEPT}
        className={styles.input}
        onChange={handleChange}
        aria-label={title}
      />
    </label>
  )
}
