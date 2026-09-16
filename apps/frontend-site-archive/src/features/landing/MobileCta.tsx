import { PixelLink } from '@/components/PixelButton'
import styles from './MobileCta.module.css'

/** Кнопка заявки, закреплённая у нижнего края на узких экранах. */
export function MobileCta({
  visible,
  label,
  href,
}: {
  visible: boolean
  label: string
  href: string
}) {
  return (
    <PixelLink
      href={href}
      variant="muted"
      size="xs"
      className={styles.root}
      data-visible={visible}
      tabIndex={visible ? undefined : -1}
    >
      {label}
    </PixelLink>
  )
}
