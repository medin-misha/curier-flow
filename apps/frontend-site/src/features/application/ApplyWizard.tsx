'use client'

import Link from 'next/link'
import { LanguageSwitcher } from '@/components/LanguageSwitcher'
import { PixelButton } from '@/components/PixelButton'
import { getMessages } from '@/i18n/messages'
import { localePath } from '@/i18n/locales'
import type { Locale } from '@/i18n/locales'
import { ProgressSegments } from './ProgressSegments'
import { StepContacts } from './steps/StepContacts'
import { StepDocuments } from './steps/StepDocuments'
import { StepIdentity } from './steps/StepIdentity'
import { StepReview } from './steps/StepReview'
import { SuccessScreen } from './SuccessScreen'
import { LAST_STEP } from './form.types'
import { useApplyWizard } from './useApplyWizard'
import styles from './ApplyWizard.module.css'

/** Форма заявки: шапка с прогрессом, текущий шаг и закреплённая нижняя панель. */
export function ApplyWizard({ locale = 'ru' }: { locale?: Locale }) {
  const copy = getMessages(locale).application
  const wizard = useApplyWizard(undefined, locale)

  if (wizard.sent) {
    return (
      <SuccessScreen
        messenger={wizard.form.messenger}
        existing={wizard.submissionOutcome === 'existing'}
        locale={locale}
      />
    )
  }

  const { step, error, submitting } = wizard

  return (
    <>
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <div className={styles.headerTop}>
            <Link href={localePath(locale, 'landing')} className={styles.back}>
              {copy.back}
            </Link>
            <div className={styles.headerTools}>
              <img src="/logo.svg" alt="May Fleet Solutions" className={styles.logo} />
              <LanguageSwitcher locale={locale} route="apply" />
            </div>
          </div>

          <div className={styles.headerMeta}>
            <span className={styles.counter} data-testid="step-counter">
              {copy.step}{' '}
              <span className={styles.counterCurrent}>{String(step).padStart(2, '0')}</span> /{' '}
              <span className={styles.counterTotal}>{String(LAST_STEP).padStart(2, '0')}</span>
            </span>
            <span className={styles.stepLabel}>{copy.stepLabels[step - 1]}</span>
          </div>

          <ProgressSegments step={step} />
        </div>
      </header>

      {step === 1 ? <StepIdentity wizard={wizard} locale={locale} /> : null}
      {step === 2 ? <StepContacts wizard={wizard} locale={locale} /> : null}
      {step === 3 ? <StepDocuments wizard={wizard} locale={locale} /> : null}
      {step === 4 ? <StepReview wizard={wizard} locale={locale} /> : null}

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
              aria-label={copy.backAria}
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
            {step < LAST_STEP ? copy.next : submitting ? copy.sending : copy.submit}
          </PixelButton>
        </div>
      </div>
    </>
  )
}
