import type { Metadata } from 'next'
import type { ReactNode } from 'react'
import { Manrope, Press_Start_2P } from 'next/font/google'
import './globals.css'

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

export const metadata: Metadata = {
  title: 'May Fleet Solutions — работа курьером Bolt Food в Чехии',
  description:
    'Подключение к Bolt Food, аренда электровелосипеда и термосумка — одной заявкой. Комиссия флотилии 10%.',
}

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ru" className={`${manrope.variable} ${pixel.variable}`}>
      <body>{children}</body>
    </html>
  )
}
