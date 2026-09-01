import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import type { ReactNode } from 'react'
import { Manrope, Press_Start_2P } from 'next/font/google'
import { getMessages } from '@/i18n/messages'
import { isLocalizedLocale, localePath, localizedLocales } from '@/i18n/locales'
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

export function generateStaticParams() {
  return localizedLocales.map((locale) => ({ locale }))
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>
}): Promise<Metadata> {
  const { locale } = await params
  if (!isLocalizedLocale(locale)) return {}

  return {
    ...getMessages(locale).metadata.landing,
    alternates: {
      canonical: localePath(locale, 'landing'),
      languages: { ru: '/', en: '/en', cs: '/cs' },
    },
  }
}

export default async function LocalizedLayout({
  children,
  params,
}: {
  children: ReactNode
  params: Promise<{ locale: string }>
}) {
  const { locale } = await params
  if (!isLocalizedLocale(locale)) notFound()

  return (
    <html lang={locale} className={`${manrope.variable} ${pixel.variable}`}>
      <body>{children}</body>
    </html>
  )
}
