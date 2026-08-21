import type { Spec } from './scene.types'
import styles from './SpecBlock.module.css'

/** Характеристика велосипеда у края экрана. */
export function SpecBlock({ spec, align }: { spec: Spec; align: 'left' | 'right' }) {
  return (
    <div className={styles.root} data-align={align}>
      <div className={styles.label}>{spec.label}</div>
      <div className={styles.value}>{spec.value}</div>
      <div className={styles.note}>{spec.note}</div>
    </div>
  )
}
