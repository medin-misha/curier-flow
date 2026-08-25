import { describe, expect, it } from 'vitest'
import { emptyForm } from './form.types'
import { submitApplication, toFormData } from './submitApplication'

const passport = new File(['x'], 'passport.png', { type: 'image/png' })
const visa = new File(['x'], 'visa.png', { type: 'image/png' })

const payload = {
  form: { ...emptyForm, fullName: 'Ivan Ivanov', consent: true },
  files: { passport, visa },
}

describe('toFormData', () => {
  it('кладёт каждое поле формы строкой', () => {
    const data = toFormData(payload)

    for (const [key, value] of Object.entries(payload.form)) {
      expect(data.get(key)).toBe(String(value))
    }
    expect(data.get('consent')).toBe('true')
  })

  it('кладёт оба скана файлами', () => {
    const data = toFormData(payload)

    expect(data.get('passport')).toBe(passport)
    expect(data.get('visa')).toBe(visa)
  })

  it('пропускает незагруженные файлы', () => {
    const data = toFormData({ form: emptyForm, files: { passport: null, visa: null } })

    expect(data.has('passport')).toBe(false)
    expect(data.has('visa')).toBe(false)
  })
})

describe('submitApplication', () => {
  it('отвечает успехом', async () => {
    await expect(submitApplication(payload)).resolves.toEqual({ ok: true })
  })
})
