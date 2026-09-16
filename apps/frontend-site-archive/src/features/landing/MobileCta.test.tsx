import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { MobileCta } from './MobileCta'

describe('MobileCta', () => {
  it('рисует ссылку с переданными надписью и адресом', () => {
    render(<MobileCta visible label="Оставить заявку" href="/apply" />)

    expect(screen.getByRole('link', { name: 'Оставить заявку' })).toHaveAttribute('href', '/apply')
  })

  it('скрытая кнопка выключена для клавиатуры', () => {
    const { rerender } = render(<MobileCta visible={false} label="Оставить заявку" href="/apply" />)

    const hidden = screen.getByRole('link', { name: 'Оставить заявку' })
    expect(hidden).toHaveAttribute('data-visible', 'false')
    expect(hidden).toHaveAttribute('tabindex', '-1')

    rerender(<MobileCta visible label="Оставить заявку" href="/apply" />)
    const shown = screen.getByRole('link', { name: 'Оставить заявку' })
    expect(shown).toHaveAttribute('data-visible', 'true')
    expect(shown).not.toHaveAttribute('tabindex')
  })
})
