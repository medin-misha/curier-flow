'use client'

import { useEffect, useRef, useState } from 'react'
import { getMessages } from '@/i18n/messages'
import { localePath } from '@/i18n/locales'
import type { Locale } from '@/i18n/locales'
import { MobileCta } from './MobileCta'
import { SiteFooter } from './SiteFooter'
import { SiteHeader } from './SiteHeader'
import type { Scene } from './scene.types'
import { sceneEyebrow } from './sceneEyebrow'
import { SceneDots } from './SceneDots'
import { ScrollHint } from './ScrollHint'
import { TransportScene } from './scenes/TransportScene'
import { IntroScene } from './scenes/IntroScene'
import { useActiveScene } from './useActiveScene'
import styles from './ScrollStage.module.css'

/**
 * CTA появляется, когда первый экран пролистан.
 *
 * Это порог глубины скролла, а не номер конкретной сцены: добавление
 * велосипеда его не меняет.
 */
const CTA_FROM_SCENE = 1

/**
 * Каркас скролл-сцены.
 *
 * Единственное место, где известен активный индекс. Высота трека, число точек
 * и цели меню считаются из массива сцен.
 */
export function ScrollStage({ scenes, locale = 'ru' }: { scenes: Scene[]; locale?: Locale }) {
  const active = useActiveScene(scenes.length)
  const copy = getMessages(locale).landing
  const trackRef = useRef<HTMLElement | null>(null)
  const [contactsReached, setContactsReached] = useState(false)
  const ctaVisible = active >= CTA_FROM_SCENE

  useEffect(() => {
    const track = trackRef.current
    if (!track) return

    const update = () => {
      // Футер начинается сразу после track: его верхняя граница — точка
      // перехода к секции «05 / КОНТАКТЫ».
      setContactsReached(track.getBoundingClientRect().bottom <= window.innerHeight)
    }

    update()
    window.addEventListener('scroll', update, { passive: true })
    window.addEventListener('resize', update)

    return () => {
      window.removeEventListener('scroll', update)
      window.removeEventListener('resize', update)
    }
  }, [scenes.length])

  return (
    <>
      <SiteHeader scenes={scenes} active={active} ctaVisible={ctaVisible} locale={locale} />

      <section
        ref={trackRef}
        className={styles.track}
        style={{ height: `${scenes.length * 100}dvh` }}
        data-scene-count={scenes.length}
        data-testid="scroll-track"
      >
        <div className={styles.viewport} data-testid="scroll-viewport">
          {scenes.map((scene, index) => {
            if (scene.kind === 'intro') {
              return (
                <IntroScene
                  key={scene.id}
                  scene={scene}
                  index={index}
                  active={active === index}
                />
              )
            }

            if (scene.kind === 'transport') {
              return (
                <TransportScene
                  key={scene.id}
                  scene={scene}
                  index={index}
                  active={active === index}
                  revealed={active >= index}
                />
              )
            }

            return null
          })}
        </div>
      </section>

      <MobileCta
        visible={ctaVisible}
        label={copy.applyCta}
        href={localePath(locale, 'apply')}
      />
      <SceneDots count={scenes.length} active={active} />
      <ScrollHint hidden={contactsReached} locale={locale} />
      <SiteFooter
        eyebrow={sceneEyebrow(scenes.length, copy.contactsEyebrow)}
        locale={locale}
      />
    </>
  )
}
