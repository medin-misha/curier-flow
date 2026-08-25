import Link from 'next/link'
import type { AnchorHTMLAttributes, ButtonHTMLAttributes } from 'react'
import styles from './PixelButton.module.css'

export type PixelVariant = 'primary' | 'muted' | 'cta' | 'ghost'
export type PixelSize = 'xs' | 'sm' | 'md'

function classes(...values: (string | undefined)[]): string {
  return values.filter(Boolean).join(' ')
}

/**
 * `data-*` разрешены явно: состояние передаётся в CSS атрибутами, а для
 * пользовательского компонента TypeScript иначе считает их лишним свойством.
 */
type DataAttributes = { [key: `data-${string}`]: string | number | boolean | undefined }

export interface PixelButtonProps extends ButtonHTMLAttributes<HTMLButtonElement>, DataAttributes {
  variant?: PixelVariant
  size?: PixelSize
}

/** Кнопка со скошенными углами и пиксельной фаской. */
export function PixelButton({
  variant = 'primary',
  size = 'md',
  className,
  type = 'button',
  ...rest
}: PixelButtonProps) {
  return (
    <button
      {...rest}
      type={type}
      data-variant={variant}
      data-size={size}
      className={classes(styles.root, className)}
    />
  )
}

export interface PixelLinkProps extends AnchorHTMLAttributes<HTMLAnchorElement>, DataAttributes {
  href: string
  variant?: PixelVariant
  size?: PixelSize
}

/** Ссылка в оформлении кнопки. */
export function PixelLink({
  href,
  variant = 'primary',
  size = 'md',
  className,
  ...rest
}: PixelLinkProps) {
  return (
    <Link
      {...rest}
      href={href}
      data-variant={variant}
      data-size={size}
      className={classes(styles.root, className)}
    />
  )
}
