'use client'

import { LanguageSwitcher } from '@/components/LanguageSwitcher'
import { PixelLink } from '@/components/PixelButton'
import { getMessages } from '@/i18n/messages'
import { localePath } from '@/i18n/locales'
import type { Locale } from '@/i18n/locales'
import type { Scene } from './scene.types'
import { activeNavKey, navTargets } from './sceneNavigation'
import { scrollToScene } from './sceneScroll'
import styles from './SiteHeader.module.css'

/** Шапка: логотип, меню по сценам, переключатель языка и CTA. */
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

  return (
    <header className={styles.root}>
      <div className={styles.top}>
        <div className={styles.brand}>
          <img src="/logo.svg" alt="May Fleet Solutions" className={styles.logo} />
        </div>

        <div className={styles.topControls}>
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
