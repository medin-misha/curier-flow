import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from 'react'
import styles from './Field.module.css'

/** Подпись, поле и подсказка одним блоком. */
export function Field({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: ReactNode
}) {
  return (
    <label className={styles.root}>
      <span className={styles.label}>{label}</span>
      {children}
      {hint ? <span className={styles.hint}>{hint}</span> : null}
    </label>
  )
}

export function TextInput({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...rest} className={[styles.input, className].filter(Boolean).join(' ')} />
}

export function SelectInput({ className, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...rest} className={[styles.input, styles.select, className].filter(Boolean).join(' ')} />
  )
}
