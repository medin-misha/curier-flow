import { describe, expect, it } from 'vitest'
import { isLocalizedLocale, localePath } from './locales'

describe('localePath', () => {
  it('сохраняет исходные русские URL', () => {
    expect(localePath('ru', 'landing')).toBe('/')
    expect(localePath('ru', 'apply')).toBe('/apply')
  })

  it('добавляет языковой префикс английской и чешской версиям', () => {
    expect(localePath('en', 'landing')).toBe('/en')
    expect(localePath('en', 'apply')).toBe('/en/apply')
    expect(localePath('cs', 'landing')).toBe('/cs')
    expect(localePath('cs', 'apply')).toBe('/cs/apply')
  })
})

describe('isLocalizedLocale', () => {
  it('не пропускает произвольный динамический сегмент как язык', () => {
    expect(isLocalizedLocale('en')).toBe(true)
    expect(isLocalizedLocale('cs')).toBe(true)
    expect(isLocalizedLocale('ru')).toBe(false)
    expect(isLocalizedLocale('de')).toBe(false)
  })
})
