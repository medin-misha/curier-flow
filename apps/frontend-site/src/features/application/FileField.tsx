import type { ChangeEvent } from 'react'
import { DOCUMENT_FILE_ACCEPT } from './validation'
import styles from './FileField.module.css'

/** Поле загрузки скана: сам инпут скрыт, кликом работает вся плашка. */
export function FileField({
  title,
  file,
  order,
  onSelect,
}: {
  title: string
  file: File | null
  /** Номер на значке, пока файл не выбран. */
  order: string
  onSelect: (file: File | null) => void
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
        <span className={styles.fileName}>{file?.name ?? 'Нажми, чтобы загрузить'}</span>
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
