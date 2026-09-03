'use client'

import { useEffect, useRef } from 'react'
import type { CSSProperties } from 'react'
import type { TransportScene as TransportSceneData } from '../scene.types'
import { sceneEyebrow } from '../sceneEyebrow'
import styles from './TransportScene.module.css'

/**
 * Единая сцена электро-транспорта: медиа выезжает снизу, поверх — общее
 * предложение и описание.
 *
 * `revealed` двигает слой, `active` проявляет текст. Слой остаётся на месте,
 * пока над ним выезжает следующая сцена, поэтому это разные флаги.
 */
export function TransportScene({
  scene,
  index,
  active,
  revealed,
}: {
  scene: TransportSceneData
  index: number
  active: boolean
  revealed: boolean
}) {
  const video = useRef<HTMLVideoElement | null>(null)
  const played = useRef(false)

  // Источник видео подставляется только у показанной сцены, чтобы не загружать
  // декоративное медиа при первом открытии лендинга.
  const wasRevealed = useRef(false)
  if (revealed) wasRevealed.current = true

  useEffect(() => {
    if (!active || played.current) return
    const element = video.current
    if (!element) return

    played.current = true
    // Автоплей может быть запрещён политикой браузера — постер остаётся на месте.
    void element.play().catch(() => {})
  }, [active])

  const sceneIndexStyle = { '--scene-index': index } as CSSProperties

  return (
    <>
      <div
        className={styles.layer}
        data-revealed={revealed}
        data-testid={`transport-layer-${scene.id}`}
        style={{ ...sceneIndexStyle, '--focus': scene.media.focus } as CSSProperties}
      >
        {scene.media.video ? (
          <video
            ref={video}
            className={styles.media}
            src={wasRevealed.current ? scene.media.video : undefined}
            poster={scene.media.poster}
            muted
            playsInline
            preload="metadata"
            data-testid={`transport-video-${scene.id}`}
          />
        ) : (
          <img
            className={styles.media}
            src={scene.media.poster}
            alt=""
            data-testid={`transport-poster-${scene.id}`}
          />
        )}
        <div className={styles.veil} />
      </div>

      <div
        className={styles.content}
        data-active={active}
        inert={!active}
        data-testid={`transport-content-${scene.id}`}
        style={sceneIndexStyle}
      >
        <div className={styles.heading}>
          <div className={styles.eyebrow}>{sceneEyebrow(index, scene.eyebrow)}</div>
          <h2 className={styles.title}>{scene.title}</h2>
        </div>

        <div className={styles.details}>
          {scene.description.map((paragraph, paragraphIndex) => (
            <p key={paragraphIndex} className={styles.description}>
              {paragraph}
            </p>
          ))}
        </div>
      </div>
    </>
  )
}
