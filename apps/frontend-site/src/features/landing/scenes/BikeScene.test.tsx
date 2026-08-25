import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { BikeScene as BikeSceneData } from '../scene.types'
import { BikeScene } from './BikeScene'

const scene: BikeSceneData = {
  kind: 'bike',
  id: 'bike-urban-e1',
  bike: {
    slug: 'urban-e1',
    name: 'MFS Urban E1',
    media: {
      poster: '/bikes/urban-e1/poster.png',
      video: '/bikes/urban-e1/loop.mp4',
      focus: '58%',
    },
    specs: [
      { label: 'АКБ', value: '48V · 20Ah', note: 'зарядка 4–5 часов' },
      { label: 'ЗАПАС ХОДА', value: 'до 65 км', note: 'на одном заряде' },
    ],
    description: ['Электровелосипед-фэтбайк для города.'],
    price: { amount: 'от 1750 CZK', period: 'в неделю' },
  },
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

describe('BikeScene', () => {
  it('рисует обе характеристики', () => {
    render(<BikeScene scene={scene} index={3} active revealed />)

    expect(screen.getByText('АКБ')).toBeInTheDocument()
    expect(screen.getByText('48V · 20Ah')).toBeInTheDocument()
    expect(screen.getByText('ЗАПАС ХОДА')).toBeInTheDocument()
    expect(screen.getByText('до 65 км')).toBeInTheDocument()
  })

  it('рисует описание и цену', () => {
    render(<BikeScene scene={scene} index={3} active revealed />)

    expect(screen.getByText('Электровелосипед-фэтбайк для города.')).toBeInTheDocument()
    expect(screen.getByText('от 1750 CZK в неделю')).toBeInTheDocument()
  })

  it('держит слой убранным, пока сцена не достигнута', () => {
    render(<BikeScene scene={scene} index={3} active={false} revealed={false} />)

    expect(screen.getByTestId('bike-layer-bike-urban-e1')).toHaveAttribute('data-revealed', 'false')
    expect(play).not.toHaveBeenCalled()
  })

  it('оставляет слой на месте, когда сверху выехала следующая сцена', () => {
    render(<BikeScene scene={scene} index={3} active={false} revealed />)

    expect(screen.getByTestId('bike-layer-bike-urban-e1')).toHaveAttribute('data-revealed', 'true')
    expect(screen.getByTestId('bike-content-bike-urban-e1')).toHaveAttribute('data-active', 'false')
  })

  it('запускает видео при активации и только один раз', () => {
    const { rerender } = render(<BikeScene scene={scene} index={3} active revealed />)
    expect(play).toHaveBeenCalledOnce()

    rerender(<BikeScene scene={scene} index={3} active={false} revealed />)
    rerender(<BikeScene scene={scene} index={3} active revealed />)
    expect(play).toHaveBeenCalledOnce()
  })

  it('подставляет источник видео только после показа сцены', () => {
    const { rerender } = render(<BikeScene scene={scene} index={3} active={false} revealed={false} />)
    const video = screen.getByTestId('bike-video-bike-urban-e1')

    expect(video).not.toHaveAttribute('src')
    expect(video).toHaveAttribute('poster', '/bikes/urban-e1/poster.png')

    rerender(<BikeScene scene={scene} index={3} active revealed />)
    expect(video).toHaveAttribute('src', '/bikes/urban-e1/loop.mp4')

    // Сцена уехала вверх — уже загруженный источник не отбирается обратно.
    rerender(<BikeScene scene={scene} index={3} active={false} revealed={false} />)
    expect(video).toHaveAttribute('src', '/bikes/urban-e1/loop.mp4')
  })

  it('обходится постером, когда видео у велосипеда нет', () => {
    const withoutVideo: BikeSceneData = {
      ...scene,
      bike: { ...scene.bike, media: { poster: '/bikes/x/poster.png', focus: '50%' } },
    }
    render(<BikeScene scene={withoutVideo} index={3} active revealed />)

    expect(screen.getByTestId('bike-poster-bike-urban-e1')).toHaveAttribute(
      'src',
      '/bikes/x/poster.png',
    )
    expect(document.querySelector('video')).toBeNull()
    expect(play).not.toHaveBeenCalled()
  })
})
