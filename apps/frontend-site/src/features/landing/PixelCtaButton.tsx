'use client'

import { useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { PixelLink } from '@/components/PixelButton'
import styles from './PixelCtaButton.module.css'

/** Смещения, повороты и задержки взяты из прототипа. */
const ICONS = [
  { src: '/cta/bike.png', tx: '-98px', ty: '-42px', rot: '-12deg', inDelay: '0ms', outDelay: '100ms', floatDuration: '2.6s', floatDelay: '0.1s' },
  { src: '/cta/phone.png', tx: '0px', ty: '-59px', rot: '0deg', inDelay: '60ms', outDelay: '50ms', floatDuration: '3.1s', floatDelay: '0.4s' },
  { src: '/cta/bag.png', tx: '98px', ty: '-42px', rot: '12deg', inDelay: '120ms', outDelay: '0ms', floatDuration: '2.9s', floatDelay: '0.7s' },
] as const

/** На касании подсветка держится, пока палец уже убран. */
const TOUCH_HOLD_MS = 600

export function PixelCtaButton({
  label,
  href,
  align = 'center',
}: {
  label: string
  href: string
  align?: 'center' | 'start'
}) {
  const [hot, setHot] = useState(false)
  const timer = useRef<number | null>(null)

  const clear = () => {
    if (timer.current === null) return
    window.clearTimeout(timer.current)
    timer.current = null
  }

  const heat = () => {
    clear()
    setHot(true)
  }

  const cool = () => {
    clear()
    setHot(false)
  }

  const coolAfterTouch = () => {
    clear()
    timer.current = window.setTimeout(() => setHot(false), TOUCH_HOLD_MS)
  }

  useEffect(() => clear, [])

  return (
    <div className={styles.wrap} data-hot={hot} data-align={align} data-testid="cta-wrap">
      {ICONS.map((icon) => (
        <div
          key={icon.src}
          aria-hidden="true"
          className={styles.icon}
          style={
            {
              '--tx': icon.tx,
              '--ty': icon.ty,
              '--rot': icon.rot,
              '--in-delay': icon.inDelay,
              '--out-delay': icon.outDelay,
              '--float-duration': icon.floatDuration,
              '--float-delay': icon.floatDelay,
            } as CSSProperties
          }
        >
          <img src={icon.src} alt="" width={101} height={101} />
        </div>
      ))}

      <PixelLink
        href={href}
        variant="cta"
        size="md"
        className={styles.button}
        onMouseEnter={heat}
        onMouseLeave={cool}
        onFocus={heat}
        onBlur={cool}
        onTouchStart={heat}
        onTouchEnd={coolAfterTouch}
      >
        {label}
      </PixelLink>
    </div>
  )
}
