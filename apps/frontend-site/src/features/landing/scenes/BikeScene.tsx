'use client'

import { useEffect, useRef } from 'react'
import type { CSSProperties } from 'react'
import { getMessages } from '@/i18n/messages'
import type { Locale } from '@/i18n/locales'
import { SpecBlock } from '../SpecBlock'
import type { BikeScene as BikeSceneData } from '../scene.types'
import { sceneEyebrow } from '../sceneEyebrow'
import styles from './BikeScene.module.css'

/**
 * Сцена велосипеда: медиа выезжает снизу, поверх — характеристики и цена.
 *
 * `revealed` двигает слой, `active` проявляет текст. Слой остаётся на месте,
 * пока над ним выезжает следующая сцена, поэтому это разные флаги.
 */
export function BikeScene({
  scene,
  index,
  active,
  revealed,
  locale = 'ru',
}: {
  scene: BikeSceneData
  index: number
  active: boolean
  revealed: boolean
  locale?: Locale
}) {
  const { bike } = scene
  const copy = getMessages(locale).landing
  const video = useRef<HTMLVideoElement | null>(null)
  const played = useRef(false)

  // Слои всех велосипедов монтируются сразу, поэтому источник подставляется
  // только у показанных: иначе трафик первой загрузки рос бы с числом сцен.
  // Флаг в рефе — чтобы уехавшая вверх сцена не сбрасывала уже загруженное.
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
  const [left, right] = bike.specs

  return (
    <>
      <div
        className={styles.layer}
        data-revealed={revealed}
        data-testid={`bike-layer-${scene.id}`}
        style={{ ...sceneIndexStyle, '--focus': bike.media.focus } as CSSProperties}
      >
        {bike.media.video ? (
          <video
            ref={video}
            className={styles.media}
            src={wasRevealed.current ? bike.media.video : undefined}
            poster={bike.media.poster}
            muted
            playsInline
            preload="metadata"
            data-testid={`bike-video-${scene.id}`}
          />
        ) : (
          <img
            className={styles.media}
            src={bike.media.poster}
            alt=""
            data-testid={`bike-poster-${scene.id}`}
          />
        )}
        <div className={styles.veil} />
      </div>

      <div className={styles.spec} data-side="left" data-active={active} style={sceneIndexStyle}>
        <SpecBlock spec={left} align="left" />
      </div>
      <div className={styles.spec} data-side="right" data-active={active} style={sceneIndexStyle}>
        <SpecBlock spec={right} align="right" />
      </div>

      <div
        className={styles.content}
        data-active={active}
        data-testid={`bike-content-${scene.id}`}
        style={sceneIndexStyle}
      >
        <div>
          {scene.eyebrow ? (
            <div className={styles.eyebrow}>{sceneEyebrow(index, scene.eyebrow)}</div>
          ) : null}

          {bike.description.map((paragraph, paragraphIndex) => (
            <p key={paragraphIndex} className={styles.description}>
              {paragraph}
            </p>
          ))}

          <p className={styles.price}>
            {copy.rental} —{' '}
            <span className={styles.priceValue}>
              {bike.price.amount} {bike.price.period}
            </span>
            .
          </p>
        </div>
      </div>
    </>
  )
}
