import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ProgressSegments } from './ProgressSegments'

describe('ProgressSegments', () => {
  it('делит шаги на пройденные, текущий и предстоящие', () => {
    render(<ProgressSegments step={3} />)

    const states = screen.getByText('01').parentElement?.children
    expect(Array.from(states ?? []).map((node) => node.getAttribute('data-state'))).toEqual([
      'done',
      'done',
      'current',
      'todo',
    ])
  })

  it('на первом шаге пройденных нет, на последнем нет предстоящих', () => {
    const { rerender } = render(<ProgressSegments step={1} />)
    const statesOf = () =>
      Array.from(screen.getByText('01').parentElement?.children ?? []).map((node) =>
        node.getAttribute('data-state'),
      )

    expect(statesOf()).toEqual(['current', 'todo', 'todo', 'todo'])

    rerender(<ProgressSegments step={4} />)
    expect(statesOf()).toEqual(['done', 'done', 'done', 'current'])
  })
})
