import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { GearScene as GearSceneData } from '../scene.types'
import { GearScene } from './GearScene'

const scene: GearSceneData = {
  kind: 'gear',
  id: 'gear-bag',
  eyebrow: 'ЭКИПИРОВКА',
  title: 'Термосумка-рюкзак',
  image: { src: '/gear/courier-bag.png', focus: '62%' },
  price: '750 CZK',
  badge: 'можно в счёт зарплаты',
  backLabel: '↑ Назад к велосипеду',
}

const scrollTo = vi.fn()

beforeEach(() => {
  scrollTo.mockClear()
  vi.stubGlobal('scrollTo', scrollTo)
  Object.defineProperty(window, 'innerHeight', { configurable: true, value: 800 })
})

describe('GearScene', () => {
  it('рисует подпись с номером, заголовок, цену и бейдж', () => {
    render(<GearScene scene={scene} index={4} revealed backToIndex={3} />)

    expect(screen.getByText('05 / ЭКИПИРОВКА')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Термосумка-рюкзак' })).toBeInTheDocument()
    expect(screen.getByText('750 CZK')).toBeInTheDocument()
    expect(screen.getByText('можно в счёт зарплаты')).toBeInTheDocument()
  })

  it('скрытая панель выключена для клавиатуры и мыши', () => {
    const { rerender } = render(<GearScene scene={scene} index={4} revealed={false} backToIndex={3} />)

    const wrap = screen.getByTestId('gear-wrap-gear-bag')
    expect(wrap).toHaveAttribute('data-revealed', 'false')
    expect(wrap).toHaveAttribute('inert')

    rerender(<GearScene scene={scene} index={4} revealed backToIndex={3} />)
    expect(screen.getByTestId('gear-wrap-gear-bag')).not.toHaveAttribute('inert')
  })

  it('возврат ведёт на переданный индекс, а не на предыдущую сцену', async () => {
    render(<GearScene scene={scene} index={6} revealed backToIndex={3} />)

    await userEvent.click(screen.getByRole('button', { name: '↑ Назад к велосипеду' }))

    expect(scrollTo).toHaveBeenCalledWith({ top: 2400, behavior: 'smooth' })
  })

  it('не рисует бейдж, когда его нет в сцене', () => {
    const { badge, ...withoutBadge } = scene
    void badge
    render(<GearScene scene={withoutBadge} index={4} revealed backToIndex={3} />)

    expect(screen.queryByText('можно в счёт зарплаты')).not.toBeInTheDocument()
  })
})
