import type { ButtonHTMLAttributes, ReactNode } from 'react'
import styles from './PixelChip.module.css'

export interface PixelChipProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  selected?: boolean
  /** Растягивает чип на всю ширину ячейки — для выбора мессенджера. */
  wide?: boolean
}

/** Чип выбора: город, мессенджер. */
export function PixelChip({ selected = false, wide = false, className, ...rest }: PixelChipProps) {
  return (
    <button
      {...rest}
      type="button"
      data-selected={selected}
      data-wide={wide}
      className={[styles.chip, className].filter(Boolean).join(' ')}
    />
  )
}

/** Некликабельная плашка того же вида. */
export function PixelBadge({ children }: { children: ReactNode }) {
  return <span className={styles.badge}>{children}</span>
}
