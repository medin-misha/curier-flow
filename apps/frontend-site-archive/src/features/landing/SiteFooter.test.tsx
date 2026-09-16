import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { company } from '@/content/company'
import { SiteFooter } from './SiteFooter'

describe('SiteFooter', () => {
  it('рисует реквизиты компании', () => {
    render(<SiteFooter eyebrow="06 / КОНТАКТЫ" />)

    expect(screen.getByText(company.legalName)).toBeInTheDocument()
    expect(screen.getByText(company.ico)).toBeInTheDocument()
    expect(screen.getByText(company.registration)).toBeInTheDocument()
  })

  it('рисует подпись из пропа, а не собственный номер', () => {
    render(<SiteFooter eyebrow="09 / КОНТАКТЫ" />)

    expect(screen.getByText('09 / КОНТАКТЫ')).toBeInTheDocument()
  })

  it('делает телефон и почту кликабельными', () => {
    render(<SiteFooter eyebrow="06 / КОНТАКТЫ" />)

    expect(screen.getByRole('link', { name: company.phone.display })).toHaveAttribute(
      'href',
      company.phone.href,
    )
    expect(screen.getByRole('link', { name: company.email })).toHaveAttribute(
      'href',
      `mailto:${company.email}`,
    )
  })

  it('рисует адрес, политику, город и копирайт', () => {
    render(<SiteFooter eyebrow="06 / КОНТАКТЫ" />)

    for (const line of company.addressLines) {
      expect(screen.getByText(line, { exact: false })).toBeInTheDocument()
    }
    expect(screen.getByRole('link', { name: new RegExp(company.privacyPolicy.label) })).toHaveAttribute(
      'href',
      company.privacyPolicy.href,
    )
    expect(screen.getByText(company.city)).toBeInTheDocument()
    expect(screen.getByText(company.copyright)).toBeInTheDocument()
  })
})
