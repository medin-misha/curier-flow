'use client'

import { getMessages } from '@/i18n/messages'
import { localePath } from '@/i18n/locales'
import type { Locale } from '@/i18n/locales'
import { MobileCta } from './MobileCta'
import { SiteFooter } from './SiteFooter'
import { SiteHeader } from './SiteHeader'
import { partitionScenes } from './partitionScenes'
import type { Scene } from './scene.types'
import { sceneEyebrow } from './sceneEyebrow'
import { lastBikeIndex } from './sceneNavigation'
import { SceneDots } from './SceneDots'
import { ScrollHint } from './ScrollHint'
import { BikeScene } from './scenes/BikeScene'
import { GearScene } from './scenes/GearScene'
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
 * и цели меню считаются из массива сцен, поэтому новый велосипед не требует
 * правок в этом файле.
 */
export function ScrollStage({ scenes, locale = 'ru' }: { scenes: Scene[]; locale?: Locale }) {
  const active = useActiveScene(scenes.length)
  const copy = getMessages(locale).landing
  const { stage, overlay } = partitionScenes(scenes)
  const backToIndex = Math.max(lastBikeIndex(scenes), 0)
  const ctaVisible = active >= CTA_FROM_SCENE

  return (
    <>
      <SiteHeader scenes={scenes} active={active} ctaVisible={ctaVisible} locale={locale} />

      <section
        className={styles.track}
        style={{ height: `${scenes.length * 100}dvh` }}
        data-scene-count={scenes.length}
        data-testid="scroll-track"
      >
        <div className={styles.viewport} data-testid="scroll-viewport">
          {stage.map(({ scene, index }) => {
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

            if (scene.kind === 'bike') {
              return (
                <BikeScene
                  key={scene.id}
                  scene={scene}
                  index={index}
                  active={active === index}
                  revealed={active >= index}
                  locale={locale}
                />
              )
            }

            return null
          })}
        </div>
      </section>

      {overlay.map(({ scene, index }) =>
        scene.kind === 'gear' ? (
          <GearScene
            key={scene.id}
            scene={scene}
            index={index}
            revealed={active >= index}
            backToIndex={backToIndex}
          />
        ) : null,
      )}

      <MobileCta
        visible={ctaVisible}
        label={copy.applyCta}
        href={localePath(locale, 'apply')}
      />
      <SceneDots count={scenes.length} active={active} />
      <ScrollHint hidden={scenes[active]?.kind === 'gear'} locale={locale} />
      <SiteFooter
        eyebrow={sceneEyebrow(scenes.length, copy.contactsEyebrow)}
        locale={locale}
      />
    </>
  )
}
