'use client'

import { LanguageSwitcher } from '@/components/LanguageSwitcher'
import { PixelLink } from '@/components/PixelButton'
import { getMessages } from '@/i18n/messages'
import { localePath } from '@/i18n/locales'
import type { Locale } from '@/i18n/locales'
import type { Scene } from './scene.types'
import { activeBikeName, activeNavKey, navTargets } from './sceneNavigation'
import { scrollToScene } from './sceneScroll'
import styles from './SiteHeader.module.css'

/** Шапка: логотип, меню по сценам, имя активного велосипеда и CTA. */
export function SiteHeader({
  scenes,
  active,
  ctaVisible,
  locale = 'ru',
}: {
  scenes: Scene[]
  active: number
  ctaVisible: boolean
  locale?: Locale
}) {
  const copy = getMessages(locale).landing
  const targets = navTargets(scenes, locale)
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
        <div className={styles.topControls}>
          <div
            className={styles.bikeName}
            data-visible={bikeName !== null}
            data-testid="header-bike-name"
          >
            {bikeName ?? ''}
          </div>
          <LanguageSwitcher locale={locale} route="landing" />
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
          href={localePath(locale, 'apply')}
          variant="primary"
          size="sm"
          className={styles.headerCta}
          data-visible={ctaVisible}
          tabIndex={ctaVisible ? undefined : -1}
        >
          {copy.applyCta}
        </PixelLink>
      </div>
    </header>
  )
}
