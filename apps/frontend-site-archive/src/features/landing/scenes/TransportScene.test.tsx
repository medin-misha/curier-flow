import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { TransportScene as TransportSceneData } from '../scene.types'
import { TransportScene } from './TransportScene'

const scene: TransportSceneData = {
  kind: 'transport',
  id: 'transport',
  eyebrow: 'ЭЛЕКТРОТРАНСПОРТ',
  title: 'Электро-транспорт от 1500 CZK',
  media: {
    poster: '/transport/poster.png',
    video: '/transport/loop.mp4',
    focus: '58%',
  },
  description: ['Электротранспорт для работы курьером — выбирай подходящий вариант.'],
}

const play = vi.fn(() => Promise.resolve())

beforeEach(() => {
  play.mockClear()
  Object.defineProperty(HTMLMediaElement.prototype, 'play', {
    configurable: true,
    writable: true,
    value: play,
  })
})

describe('TransportScene', () => {
  it('рисует единое предложение по электро-транспорту', () => {
    render(<TransportScene scene={scene} index={3} active revealed />)

    expect(screen.getByRole('heading', { name: 'Электро-транспорт от 1500 CZK' })).toBeInTheDocument()
    expect(
      screen.getByText('Электротранспорт для работы курьером — выбирай подходящий вариант.'),
    ).toBeInTheDocument()
  })

  it('скрывает неактивный текст от клавиатуры', () => {
    const { rerender } = render(
      <TransportScene scene={scene} index={3} active={false} revealed={false} />,
    )

    const content = screen.getByTestId('transport-content-transport')
    expect(content).toHaveAttribute('data-active', 'false')
    expect(content).toHaveAttribute('inert')

    rerender(<TransportScene scene={scene} index={3} active revealed />)
    expect(screen.getByTestId('transport-content-transport')).not.toHaveAttribute('inert')
  })

  it('держит слой убранным, пока сцена не достигнута', () => {
    render(<TransportScene scene={scene} index={3} active={false} revealed={false} />)

    expect(screen.getByTestId('transport-layer-transport')).toHaveAttribute(
      'data-revealed',
      'false',
    )
    expect(play).not.toHaveBeenCalled()
  })

  it('оставляет слой на месте, когда сверху выехала следующая сцена', () => {
    render(<TransportScene scene={scene} index={3} active={false} revealed />)

    expect(screen.getByTestId('transport-layer-transport')).toHaveAttribute(
      'data-revealed',
      'true',
    )
    expect(screen.getByTestId('transport-content-transport')).toHaveAttribute(
      'data-active',
      'false',
    )
  })

  it('запускает видео при активации и только один раз', () => {
    const { rerender } = render(<TransportScene scene={scene} index={3} active revealed />)
    expect(play).toHaveBeenCalledOnce()

    rerender(<TransportScene scene={scene} index={3} active={false} revealed />)
    rerender(<TransportScene scene={scene} index={3} active revealed />)
    expect(play).toHaveBeenCalledOnce()
  })

  it('подставляет источник видео только после показа сцены', () => {
    const { rerender } = render(
      <TransportScene scene={scene} index={3} active={false} revealed={false} />,
    )
    const video = screen.getByTestId('transport-video-transport')

    expect(video).not.toHaveAttribute('src')
    expect(video).toHaveAttribute('poster', '/transport/poster.png')

    rerender(<TransportScene scene={scene} index={3} active revealed />)
    expect(video).toHaveAttribute('src', '/transport/loop.mp4')

    // Сцена уехала вверх — уже загруженный источник не отбирается обратно.
    rerender(<TransportScene scene={scene} index={3} active={false} revealed={false} />)
    expect(video).toHaveAttribute('src', '/transport/loop.mp4')
  })

  it('обходится постером, когда видео у транспорта нет', () => {
    const withoutVideo: TransportSceneData = {
      ...scene,
      media: { poster: '/transport/only-poster.png', focus: '50%' },
    }
    render(<TransportScene scene={withoutVideo} index={3} active revealed />)

    expect(screen.getByTestId('transport-poster-transport')).toHaveAttribute(
      'src',
      '/transport/only-poster.png',
    )
    expect(document.querySelector('video')).toBeNull()
    expect(play).not.toHaveBeenCalled()
  })
})
