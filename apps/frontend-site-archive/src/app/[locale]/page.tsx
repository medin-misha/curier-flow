import { notFound } from 'next/navigation'
import { getScenes } from '@/content/scenes'
import { ScrollStage } from '@/features/landing/ScrollStage'
import { isLocalizedLocale } from '@/i18n/locales'

export default async function LocalizedLandingPage({
  params,
}: {
  params: Promise<{ locale: string }>
}) {
  const { locale } = await params
  if (!isLocalizedLocale(locale)) notFound()

  return (
    <main>
      <ScrollStage scenes={getScenes(locale)} locale={locale} />
    </main>
  )
}
