import type { Metadata } from 'next'
import type { ReactNode } from 'react'
import { Manrope, Press_Start_2P } from 'next/font/google'
import { getMessages } from '@/i18n/messages'
import '../globals.css'

const manrope = Manrope({
  subsets: ['latin', 'cyrillic'],
  weight: ['400', '500', '600', '700', '800'],
  variable: '--font-manrope',
  display: 'swap',
})

const pixel = Press_Start_2P({
  subsets: ['latin'],
  weight: '400',
  variable: '--font-pixel',
  display: 'swap',
})

const copy = getMessages('ru').metadata.landing

export const metadata: Metadata = {
  ...copy,
  alternates: {
    canonical: '/',
    languages: { ru: '/', en: '/en', cs: '/cs' },
  },
}

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ru" className={`${manrope.variable} ${pixel.variable}`}>
      <body>{children}</body>
    </html>
  )
}
