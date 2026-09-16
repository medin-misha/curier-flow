import type { Metadata } from 'next'
import { ApplyWizard } from '@/features/application/ApplyWizard'
import { getMessages } from '@/i18n/messages'

export const metadata: Metadata = {
  ...getMessages('ru').metadata.apply,
  alternates: {
    canonical: '/apply',
    languages: { ru: '/apply', en: '/en/apply', cs: '/cs/apply' },
  },
}

export default function ApplyPage() {
  return (
    <main>
      <ApplyWizard />
    </main>
  )
}
