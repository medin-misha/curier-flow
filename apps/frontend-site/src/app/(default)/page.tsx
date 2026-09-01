import { scenes } from '@/content/scenes'
import { ScrollStage } from '@/features/landing/ScrollStage'

export default function LandingPage() {
  return (
    <main>
      <ScrollStage scenes={scenes} />
    </main>
  )
}
