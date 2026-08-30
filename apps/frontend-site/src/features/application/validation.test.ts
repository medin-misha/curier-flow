import { describe, expect, it } from 'vitest'
import { emptyFiles, emptyForm } from './form.types'
import type { ApplicationFiles, ApplicationForm } from './form.types'
import {
  MAX_DOCUMENT_FILE_SIZE,
  ageOn,
  digitsOnly,
  firstInvalidStep,
  validateStep,
} from './validation'

const TODAY = new Date(2026, 7, 14)

function form(patch: Partial<ApplicationForm> = {}): ApplicationForm {
  return { ...emptyForm, ...patch }
}

function files(patch: Partial<ApplicationFiles> = {}): ApplicationFiles {
  return { ...emptyFiles, ...patch }
}

function scan(name: string): File {
  return new File(['x'], name, { type: 'image/png' })
}

const validIdentity: Partial<ApplicationForm> = {
  fullName: 'Ivan Ivanov',
  birthDate: '1998-03-10',
  city: 'Praha',
  address: 'Malá Michnovka 1095/20',
}

const validContacts: Partial<ApplicationForm> = {
  phone: '777123456',
  email: 'ivan@email.com',
  messengerContact: '+420 777 123 456',
}

const validDocuments: Partial<ApplicationForm> = {
  bankAccount: 'CZ00 0000 0000 0000 0000 0000',
  citizenship: 'Украина',
}

const bothScans = files({ passport: scan('passport.png'), visa: scan('visa.png') })

describe('digitsOnly', () => {
  it('оставляет только цифры', () => {
    expect(digitsOnly('+420 777 123 456')).toBe('420777123456')
    expect(digitsOnly('CZ00 1234')).toBe('001234')
    expect(digitsOnly('')).toBe('')
  })
})

describe('ageOn', () => {
  it('считает возраст на переданную дату', () => {
    expect(ageOn('1998-03-10', TODAY)).toBe(28)
  })

  it('не засчитывает год, если день рождения ещё не наступил', () => {
    expect(ageOn('2000-08-15', TODAY)).toBe(25)
    expect(ageOn('2000-08-14', TODAY)).toBe(26)
  })

  it('возвращает null на пустой и битой дате', () => {
    expect(ageOn('', TODAY)).toBeNull()
    expect(ageOn('не дата', TODAY)).toBeNull()
  })

  it('отвергает дату вне календаря, а не переносит её', () => {
    expect(ageOn('2024-13-40', TODAY)).toBeNull()
    expect(ageOn('2000-02-30', TODAY)).toBeNull()
  })
})

describe('validateStep, шаг 1', () => {
  it('пропускает заполненный шаг', () => {
    expect(validateStep(1, form(validIdentity), emptyFiles, TODAY)).toBe('')
  })

  it('требует имя, потом фамилию', () => {
    expect(validateStep(1, form(), emptyFiles, TODAY)).toBe('Впиши имя и фамилию.')
    expect(validateStep(1, form({ fullName: 'Ivan' }), emptyFiles, TODAY)).toBe(
      'Нужно имя и фамилия — два слова.',
    )
  })

  it('требует дату рождения', () => {
    expect(validateStep(1, form({ ...validIdentity, birthDate: '' }), emptyFiles, TODAY)).toBe(
      'Укажи дату рождения.',
    )
  })

  it('держит нижнюю границу возраста на 18 годах', () => {
    expect(
      validateStep(1, form({ ...validIdentity, birthDate: '2008-08-15' }), emptyFiles, TODAY),
    ).toBe('Работать курьером можно с 18 лет.')
    expect(
      validateStep(1, form({ ...validIdentity, birthDate: '2008-08-14' }), emptyFiles, TODAY),
    ).toBe('')
  })

  it('держит верхнюю границу возраста на 75 годах', () => {
    expect(
      validateStep(1, form({ ...validIdentity, birthDate: '1951-08-14' }), emptyFiles, TODAY),
    ).toBe('')
    expect(
      validateStep(1, form({ ...validIdentity, birthDate: '1950-08-14' }), emptyFiles, TODAY),
    ).toBe('Проверь дату рождения.')
  })

  it('требует город и адрес', () => {
    expect(validateStep(1, form({ ...validIdentity, city: '' }), emptyFiles, TODAY)).toBe(
      'Выбери или впиши город.',
    )
    expect(validateStep(1, form({ ...validIdentity, address: '  ' }), emptyFiles, TODAY)).toBe(
      'Впиши адрес проживания.',
    )
  })
})

describe('validateStep, шаг 2', () => {
  it('пропускает заполненный шаг', () => {
    expect(validateStep(2, form(validContacts), emptyFiles, TODAY)).toBe('')
  })

  it('требует ровно девять цифр в телефоне', () => {
    expect(validateStep(2, form({ ...validContacts, phone: '' }), emptyFiles, TODAY)).toBe(
      'Впиши чешский номер телефона.',
    )
    expect(validateStep(2, form({ ...validContacts, phone: '77712345' }), emptyFiles, TODAY)).toBe(
      'Чешский номер — 9 цифр после +420.',
    )
    expect(validateStep(2, form({ ...validContacts, phone: '7771234567' }), emptyFiles, TODAY)).toBe(
      'Чешский номер — 9 цифр после +420.',
    )
  })

  it('проверяет формат почты', () => {
    for (const email of ['ivan@email', 'ivanemail.com', 'ivan @email.com', '@email.com', 'ivan@']) {
      expect(validateStep(2, form({ ...validContacts, email }), emptyFiles, TODAY)).toBe(
        'Проверь почту.',
      )
    }
    expect(validateStep(2, form({ ...validContacts, email: 'ivan@email.com' }), emptyFiles, TODAY)).toBe(
      '',
    )
  })

  it('называет выбранный мессенджер в тексте ошибки', () => {
    expect(
      validateStep(
        2,
        form({ ...validContacts, messenger: 'Telegram', messengerContact: '' }),
        emptyFiles,
        TODAY,
      ),
    ).toBe('Оставь контакт в Telegram.')
  })
})

describe('validateStep, шаг 3', () => {
  it('пропускает заполненный шаг', () => {
    expect(validateStep(3, form(validDocuments), bothScans, TODAY)).toBe('')
  })

  it('требует минимум восемь цифр в счёте', () => {
    expect(validateStep(3, form({ ...validDocuments, bankAccount: 'CZ 12345' }), bothScans, TODAY)).toBe(
      'Впиши счёт в чешском банке.',
    )
    expect(
      validateStep(3, form({ ...validDocuments, bankAccount: 'CZ 1234567' }), bothScans, TODAY),
    ).toBe('Впиши счёт в чешском банке.')
    expect(
      validateStep(3, form({ ...validDocuments, bankAccount: 'CZ 12345678' }), bothScans, TODAY),
    ).toBe('')
  })

  it('требует гражданство', () => {
    expect(validateStep(3, form({ ...validDocuments, citizenship: '' }), bothScans, TODAY)).toBe(
      'Выбери гражданство.',
    )
  })

  it('требует оба скана', () => {
    expect(validateStep(3, form(validDocuments), emptyFiles, TODAY)).toBe('Загрузи скан паспорта.')
    expect(
      validateStep(3, form(validDocuments), files({ passport: scan('p.png') }), TODAY),
    ).toBe('Загрузи скан визы или ВНЖ.')
  })

  it('проверяет MIME документов', () => {
    const unsupported = new File(['x'], 'passport.gif', { type: 'image/gif' })

    expect(
      validateStep(
        3,
        form(validDocuments),
        files({ passport: unsupported, visa: scan('permit.png') }),
        TODAY,
      ),
    ).toBe('Формат файла «passport.gif» не поддерживается. Нужен PNG, JPEG, WebP или PDF.')
  })

  it('отвергает пустые и слишком большие документы', () => {
    const empty = new File([], 'empty.pdf', { type: 'application/pdf' })
    const tooLarge = new File([new Uint8Array(MAX_DOCUMENT_FILE_SIZE + 1)], 'large.pdf', {
      type: 'application/pdf',
    })

    expect(
      validateStep(
        3,
        form(validDocuments),
        files({ passport: empty, visa: scan('permit.png') }),
        TODAY,
      ),
    ).toBe('Файл «empty.pdf» пуст. Выбери документ ещё раз.')
    expect(
      validateStep(
        3,
        form(validDocuments),
        files({ passport: tooLarge, visa: scan('permit.png') }),
        TODAY,
      ),
    ).toBe('Файл «large.pdf» больше 10 МБ.')
  })
})

describe('validateStep, шаг 4', () => {
  it('требует согласие', () => {
    expect(validateStep(4, form(), emptyFiles, TODAY)).toBe('Нужно согласие на обработку данных.')
    expect(validateStep(4, form({ consent: true }), emptyFiles, TODAY)).toBe('')
  })
})

describe('firstInvalidStep', () => {
  it('находит самый ранний незаполненный шаг', () => {
    const partly = form({ ...validIdentity, ...validContacts })
    expect(firstInvalidStep(partly, emptyFiles, TODAY)).toBe(3)
  })

  it('возвращает null, когда шаги 1–3 заполнены', () => {
    const full = form({ ...validIdentity, ...validContacts, ...validDocuments })
    expect(firstInvalidStep(full, bothScans, TODAY)).toBeNull()
  })

  it('указывает на первый шаг, если пусто всё', () => {
    expect(firstInvalidStep(form(), emptyFiles, TODAY)).toBe(1)
  })
})
