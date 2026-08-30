'use client'

import { useCallback, useRef, useState } from 'react'
import type { ApplicationFiles, ApplicationForm, StepNumber } from './form.types'
import { LAST_STEP, emptyFiles, emptyForm } from './form.types'
import type { SubmitResult } from './submitApplication'
import { submitApplication } from './submitApplication'
import { PHONE_DIGITS, digitsOnly, firstInvalidStep, validateStep } from './validation'

export interface ApplyWizard {
  step: StepNumber
  form: ApplicationForm
  files: ApplicationFiles
  error: string
  submitting: boolean
  sent: boolean
  submissionOutcome: 'created' | 'existing' | null
  setField<K extends keyof ApplicationForm>(key: K, value: ApplicationForm[K]): void
  setFile(key: keyof ApplicationFiles, file: File | null): void
  goTo(step: StepNumber): void
  back(): void
  next(): Promise<void>
  /** Часы визарда: шаги берут дату отсюда, а не из new Date() в рендере. */
  now: () => Date
}

/**
 * Телефон хранится цифрами без префикса — так его проверяет валидация.
 * API-адаптер добавляет E.164-префикс +420 перед отправкой. Нормализация
 * здесь, а не в поле ввода: иначе инвариант держался бы только для одного
 * способа заполнить форму.
 */
function normalize<K extends keyof ApplicationForm>(
  key: K,
  value: ApplicationForm[K],
): ApplicationForm[K] {
  if (key !== 'phone') return value
  const digits = digitsOnly(String(value))
  const local = digits.length > PHONE_DIGITS && digits.startsWith('420') ? digits.slice(3) : digits
  return local.slice(0, PHONE_DIGITS) as ApplicationForm[K]
}

function scrollToTop(): void {
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

/** Состояние четырёхшагового визарда заявки. */
export function useApplyWizard(now: () => Date = () => new Date()): ApplyWizard {
  const [step, setStep] = useState<StepNumber>(1)
  const [form, setForm] = useState<ApplicationForm>(emptyForm)
  const [files, setFiles] = useState<ApplicationFiles>(emptyFiles)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [sent, setSent] = useState(false)
  const [submissionOutcome, setSubmissionOutcome] = useState<'created' | 'existing' | null>(null)
  const inFlight = useRef(false)

  const setField = useCallback<ApplyWizard['setField']>((key, value) => {
    setForm((current) => ({ ...current, [key]: normalize(key, value) }))
    setError('')
  }, [])

  const setFile = useCallback<ApplyWizard['setFile']>((key, file) => {
    setFiles((current) => ({ ...current, [key]: file }))
    setError('')
  }, [])

  const goTo = useCallback((target: StepNumber) => {
    setStep(target)
    setError('')
    scrollToTop()
  }, [])

  const back = useCallback(() => {
    if (step === 1) return
    goTo((step - 1) as StepNumber)
  }, [goTo, step])

  const next = useCallback(async () => {
    // Реф, а не submitting: состояние обновляется асинхронно, и два быстрых
    // вызова успели бы прочитать его до первого setSubmitting.
    if (inFlight.current) return

    const today = now()

    const stepError = validateStep(step, form, files, today)
    if (stepError) {
      setError(stepError)
      return
    }

    if (step < LAST_STEP) {
      goTo((step + 1) as StepNumber)
      return
    }

    // Шаги перепроверяются целиком: пользователь мог вернуться и стереть введённое.
    const broken = firstInvalidStep(form, files, today)
    if (broken !== null) {
      setStep(broken)
      setError(validateStep(broken, form, files, today))
      scrollToTop()
      return
    }

    inFlight.current = true
    setSubmitting(true)

    let result: SubmitResult
    try {
      result = await submitApplication({ form, files })
    } catch {
      // Сеть могла отвалиться: разблокируем форму и даём человеку повторить.
      setError('Не удалось отправить заявку. Проверь соединение и попробуй ещё раз.')
      return
    } finally {
      setSubmitting(false)
      inFlight.current = false
    }

    if (!result.ok) {
      setError(result.message)
      return
    }

    setError('')
    setSubmissionOutcome(result.outcome)
    setSent(true)
    scrollToTop()
  }, [files, form, goTo, now, step])

  return {
    step,
    form,
    files,
    error,
    submitting,
    sent,
    submissionOutcome,
    setField,
    setFile,
    goTo,
    back,
    next,
    now,
  }
}
