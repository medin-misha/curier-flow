'use client'

import Link from 'next/link'
import { PixelButton } from '@/components/PixelButton'
import { ProgressSegments } from './ProgressSegments'
import { StepContacts } from './steps/StepContacts'
import { StepDocuments } from './steps/StepDocuments'
import { StepIdentity } from './steps/StepIdentity'
import { StepReview } from './steps/StepReview'
import { SuccessScreen } from './SuccessScreen'
import { LAST_STEP, STEP_LABELS } from './form.types'
import { useApplyWizard } from './useApplyWizard'
import styles from './ApplyWizard.module.css'

/** Форма заявки: шапка с прогрессом, текущий шаг и закреплённая нижняя панель. */
export function ApplyWizard() {
  const wizard = useApplyWizard()

  if (wizard.sent) {
    return (
      <SuccessScreen
        messenger={wizard.form.messenger}
        existing={wizard.submissionOutcome === 'existing'}
      />
    )
  }

  const { step, error, submitting } = wizard

  return (
    <>
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <div className={styles.headerTop}>
            <Link href="/" className={styles.back}>
              ← Назад
            </Link>
            <img src="/logo.svg" alt="May Fleet Solutions" className={styles.logo} />
          </div>

          <div className={styles.headerMeta}>
            <span className={styles.counter} data-testid="step-counter">
              Шаг <span className={styles.counterCurrent}>{String(step).padStart(2, '0')}</span> /{' '}
              <span className={styles.counterTotal}>{String(LAST_STEP).padStart(2, '0')}</span>
            </span>
            <span className={styles.stepLabel}>{STEP_LABELS[step - 1]}</span>
          </div>

          <ProgressSegments step={step} />
        </div>
      </header>

      {step === 1 ? <StepIdentity wizard={wizard} /> : null}
      {step === 2 ? <StepContacts wizard={wizard} /> : null}
      {step === 3 ? <StepDocuments wizard={wizard} /> : null}
      {step === 4 ? <StepReview wizard={wizard} /> : null}

      <div className={styles.footer}>
        {error ? (
          <div className={styles.error} role="alert">
            {error}
          </div>
        ) : null}

        <div className={styles.actions}>
          {step > 1 ? (
            <PixelButton
              variant="ghost"
              size="md"
              className={styles.backButton}
              onClick={wizard.back}
              aria-label="Назад"
            >
              ←
            </PixelButton>
          ) : null}

          <PixelButton
            variant="primary"
            size="md"
            className={styles.nextButton}
            onClick={() => void wizard.next()}
            disabled={submitting}
          >
            {step < LAST_STEP ? 'Далее' : submitting ? 'Отправляем…' : 'Отправить заявку'}
          </PixelButton>
        </div>
      </div>
    </>
  )
}
