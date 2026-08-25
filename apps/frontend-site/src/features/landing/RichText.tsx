import { Fragment } from 'react'
import type { TextSegment } from './scene.types'
import styles from './RichText.module.css'

/**
 * Текст с выделенными фрагментами.
 *
 * Сегменты вместо мини-разметки: конфиг остаётся типизированным,
 * и в проекте не заводится парсер ради двух жирных слов.
 */
export function RichText({ segments }: { segments: TextSegment[] }) {
  return (
    <>
      {segments.map((segment, index) =>
        typeof segment === 'string' ? (
          <Fragment key={index}>{segment}</Fragment>
        ) : (
          <strong key={index} className={styles.em}>
            {segment.em}
          </strong>
        ),
      )}
    </>
  )
}
