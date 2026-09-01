import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import { ApplyWizard } from '@/features/application/ApplyWizard'
import { getMessages } from '@/i18n/messages'
import { isLocalizedLocale, localePath } from '@/i18n/locales'

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>
}): Promise<Metadata> {
  const { locale } = await params
  if (!isLocalizedLocale(locale)) return {}

  return {
    ...getMessages(locale).metadata.apply,
    alternates: {
      canonical: localePath(locale, 'apply'),
      languages: { ru: '/apply', en: '/en/apply', cs: '/cs/apply' },
    },
  }
}

export default async function LocalizedApplyPage({
  params,
}: {
  params: Promise<{ locale: string }>
}) {
  const { locale } = await params
  if (!isLocalizedLocale(locale)) notFound()

  return (
    <main>
      <ApplyWizard locale={locale} />
    </main>
  )
}
