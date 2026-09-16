import type { CSSProperties } from 'react'
import { PixelCtaButton } from '../PixelCtaButton'
import { RichText } from '../RichText'
import type { IntroScene as IntroSceneData } from '../scene.types'
import { sceneEyebrow } from '../sceneEyebrow'
import styles from './IntroScene.module.css'

/** Вводная сцена: фоновая фотография с кроссфейдом и текстовый блок поверх. */
export function IntroScene({
  scene,
  index,
  active,
}: {
  scene: IntroSceneData
  index: number
  active: boolean
}) {
  const layerStyle = {
    '--scene-index': index,
    '--focus-mobile': scene.background.focusMobile,
    '--focus-desktop': scene.background.focusDesktop,
  } as CSSProperties

  return (
    <>
      <div
        className={styles.layer}
        data-active={active}
        data-testid={`intro-layer-${scene.id}`}
        style={layerStyle}
      >
        <img src={scene.background.src} alt="" className={styles.image} />
        <div className={styles.veil} />
      </div>

      <div
        className={styles.content}
        data-active={active}
        inert={!active}
        data-align={scene.align ?? 'spread'}
        data-first={index === 0}
        data-testid={`intro-content-${scene.id}`}
        style={{ '--scene-index': index } as CSSProperties}
      >
        <div>
          <div className={styles.eyebrow}>{sceneEyebrow(index, scene.eyebrow)}</div>
          <h1 className={styles.title}>{scene.title}</h1>
        </div>

        {scene.body.kind === 'bullets' ? (
          <div className={styles.bullets}>
            {scene.body.items.map((bullet, bulletIndex) => (
              <div key={bulletIndex} className={styles.bullet}>
                <span className={styles.marker} data-kind={bullet.markerKind}>
                  {bullet.marker}
                </span>
                <span className={styles.bulletText}>
                  <RichText segments={bullet.text} />
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className={styles.paragraphs}>
            {scene.body.items.map((segments, paragraphIndex) => (
              <p key={paragraphIndex} className={styles.paragraph}>
                <RichText segments={segments} />
              </p>
            ))}
          </div>
        )}

        {scene.cta ? (
          <div className={styles.ctaRow}>
            <PixelCtaButton label={scene.cta.label} href={scene.cta.href} />
          </div>
        ) : null}
      </div>
    </>
  )
}
