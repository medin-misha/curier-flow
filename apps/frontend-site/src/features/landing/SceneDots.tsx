import styles from './SceneDots.module.css'

/** Индикатор прогресса: по точке на сцену. */
export function SceneDots({ count, active }: { count: number; active: number }) {
  return (
    <div className={styles.root} aria-hidden="true" data-testid="scene-dots">
      {Array.from({ length: count }, (_, index) => (
        <span key={index} className={styles.dot} data-active={index === active} />
      ))}
    </div>
  )
}
