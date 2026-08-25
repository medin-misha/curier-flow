'use client'

import type { Scene } from './scene.types'
import { activeBikeName, activeNavKey, navTargets } from './sceneNavigation'
import { scrollToScene } from './sceneScroll'
import { PixelLink } from '@/components/PixelButton'
import styles from './SiteHeader.module.css'

/** Шапка: логотип, меню по сценам, имя активного велосипеда и CTA. */
export function SiteHeader({
  scenes,
  active,
  ctaVisible,
}: {
  scenes: Scene[]
  active: number
  ctaVisible: boolean
}) {
  const targets = navTargets(scenes)
  const currentKey = activeNavKey(scenes, active)
  const bikeName = activeBikeName(scenes, active)

  return (
    <header className={styles.root}>
      <div className={styles.top}>
        <div className={styles.brand}>
          <img src="/logo.svg" alt="May Fleet Solutions" className={styles.logo} />
          <span className={styles.brandName}>May Fleet Solutions</span>
        </div>

        {/*
          Имя остаётся в разметке при смене сцены, чтобы уезжало плавно,
          а не пропадало вместе с узлом.
        */}
        <div
          className={styles.bikeName}
          data-visible={bikeName !== null}
          data-testid="header-bike-name"
        >
          {bikeName ?? ''}
        </div>
      </div>

      <div className={styles.bottom}>
        <nav className={styles.nav}>
          {targets.map((target) => (
            <button
              key={target.key}
              type="button"
              className={styles.navLink}
              data-active={target.key === currentKey}
              onClick={() => scrollToScene(target.index)}
            >
              {target.label}
            </button>
          ))}
        </nav>

        <PixelLink
          href="/apply"
          variant="primary"
          size="sm"
          className={styles.headerCta}
          data-visible={ctaVisible}
          tabIndex={ctaVisible ? undefined : -1}
        >
          Оставить заявку
        </PixelLink>
      </div>
    </header>
  )
}
