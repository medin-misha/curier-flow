import styles from './ScrollHint.module.css'

/** Подсказка «листай ↓». Гаснет на последней сцене. */
export function ScrollHint({ hidden }: { hidden: boolean }) {
  return (
    <div className={styles.root} data-hidden={hidden} aria-hidden="true">
      листай ↓
    </div>
  )
}
