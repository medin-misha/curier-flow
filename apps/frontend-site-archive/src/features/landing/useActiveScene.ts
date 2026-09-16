'use client'

import { useEffect, useState } from 'react'
import { sceneIndexFromScroll } from './sceneScroll'

/**
 * Индекс активной сцены.
 *
 * Обработчик скролла троттлится через requestAnimationFrame: браузер
 * присылает событие чаще, чем есть смысл пересчитывать состояние.
 */
export function useActiveScene(sceneCount: number): number {
  const [index, setIndex] = useState(0)

  useEffect(() => {
    let frame = 0

    const update = () => {
      frame = 0
      setIndex(sceneIndexFromScroll(window.scrollY, window.innerHeight, sceneCount))
    }

    const schedule = () => {
      if (frame) return
      frame = window.requestAnimationFrame(update)
    }

    window.addEventListener('scroll', schedule, { passive: true })
    window.addEventListener('resize', schedule)
    update()

    return () => {
      if (frame) window.cancelAnimationFrame(frame)
      window.removeEventListener('scroll', schedule)
      window.removeEventListener('resize', schedule)
    }
  }, [sceneCount])

  return index
}
