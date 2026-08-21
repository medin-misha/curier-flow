import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { RichText } from './RichText'

describe('RichText', () => {
  it('склеивает обычный текст и выделенные фрагменты', () => {
    render(
      <p>
        <RichText segments={['Комиссия флотилии — всего ', { em: '10%' }]} />
      </p>,
    )

    expect(screen.getByText(/Комиссия флотилии — всего/)).toBeInTheDocument()
    expect(screen.getByText('10%').tagName).toBe('STRONG')
  })

  it('без выделений не создаёт лишних элементов', () => {
    const { container } = render(<RichText segments={['Просто текст']} />)

    expect(container.textContent).toBe('Просто текст')
    expect(container.querySelector('strong')).toBeNull()
  })
})
