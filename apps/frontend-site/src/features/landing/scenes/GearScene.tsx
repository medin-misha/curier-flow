'use client'

import type { CSSProperties } from 'react'
import { PixelBadge } from '@/components/PixelChip'
import type { GearScene as GearSceneData } from '../scene.types'
import { sceneEyebrow } from '../sceneEyebrow'
import { scrollToScene } from '../sceneScroll'
import styles from './GearScene.module.css'

/**
 * Сцена экипировки: панель выезжает поверх страницы.
 *
 * Рендерится отдельным слоем документа, а не внутри sticky-вьюпорта, чтобы
 * футер мог перекрыть её при дальнейшем скролле.
 */
export function GearScene({
  scene,
  index,
  revealed,
  backToIndex,
}: {
  scene: GearSceneData
  index: number
  revealed: boolean
  backToIndex: number
}) {
  return (
    <div
      className={styles.wrap}
      data-revealed={revealed}
      inert={!revealed}
      data-testid={`gear-wrap-${scene.id}`}
    >
      <div className={styles.panel} style={{ '--focus': scene.image.focus } as CSSProperties}>
        <img src={scene.image.src} alt={scene.title} className={styles.image} />
        <div className={styles.veil} />

        <div className={styles.content}>
          <div className={styles.eyebrow}>{sceneEyebrow(index, scene.eyebrow)}</div>

          <div className={styles.body}>
            <h2 className={styles.title}>{scene.title}</h2>

            <div className={styles.priceRow}>
              <span className={styles.price}>{scene.price}</span>
              {scene.badge ? <PixelBadge>{scene.badge}</PixelBadge> : null}
            </div>

            <button
              type="button"
              className={styles.back}
              onClick={() => scrollToScene(backToIndex)}
            >
              {scene.backLabel}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
