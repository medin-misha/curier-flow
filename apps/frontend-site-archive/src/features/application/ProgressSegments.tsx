import type { StepNumber } from './form.types'
import { LAST_STEP } from './form.types'
import styles from './ProgressSegments.module.css'

function state(segment: number, step: StepNumber): 'done' | 'current' | 'todo' {
  if (segment < step) return 'done'
  if (segment === step) return 'current'
  return 'todo'
}

/** Сегментный индикатор: текущий шаг шире остальных. */
export function ProgressSegments({ step }: { step: StepNumber }) {
  return (
    <div className={styles.root} aria-hidden="true">
      {Array.from({ length: LAST_STEP }, (_, index) => {
        const segment = index + 1
        return (
          <div key={segment} className={styles.segment} data-state={state(segment, step)}>
            {String(segment).padStart(2, '0')}
          </div>
        )
      })}
    </div>
  )
}
