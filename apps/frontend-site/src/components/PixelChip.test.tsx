import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { PixelBadge, PixelChip } from './PixelChip'

describe('PixelChip', () => {
  it('по умолчанию не выбран', () => {
    render(<PixelChip>Praha</PixelChip>)
    expect(screen.getByRole('button', { name: 'Praha' })).toHaveAttribute('data-selected', 'false')
  })

  it('помечается выбранным и вызывает обработчик', async () => {
    const onClick = vi.fn()
    render(
      <PixelChip selected onClick={onClick}>
        Brno
      </PixelChip>,
    )

    const chip = screen.getByRole('button', { name: 'Brno' })
    expect(chip).toHaveAttribute('data-selected', 'true')

    await userEvent.click(chip)
    expect(onClick).toHaveBeenCalledOnce()
  })
})

describe('PixelBadge', () => {
  it('рисует текст без роли кнопки', () => {
    render(<PixelBadge>можно в счёт зарплаты</PixelBadge>)

    expect(screen.getByText('можно в счёт зарплаты')).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
