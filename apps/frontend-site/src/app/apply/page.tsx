import type { Metadata } from 'next'
import { ApplyWizard } from '@/features/application/ApplyWizard'

export const metadata: Metadata = {
  title: 'Заявка — May Fleet Solutions',
  description: 'Анкета курьера Bolt Food: личные данные, контакты, документы и счёт.',
}

export default function ApplyPage() {
  return (
    <main>
      <ApplyWizard />
    </main>
  )
}
