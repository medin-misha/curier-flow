import type { ApplicationFiles, ApplicationForm } from './form.types'

export interface ApplicationPayload {
  form: ApplicationForm
  files: ApplicationFiles
}

export type SubmitResult = { ok: true } | { ok: false; message: string }

/** Задержка заглушки, чтобы состояние отправки было видно в интерфейсе. */
const FAKE_LATENCY_MS = 600

/** Собирает `multipart/form-data` — тот же формат ждёт будущий бекенд. */
export function toFormData({ form, files }: ApplicationPayload): FormData {
  const data = new FormData()

  for (const [key, value] of Object.entries(form)) {
    data.append(key, String(value))
  }

  if (files.passport) data.append('passport', files.passport)
  if (files.visa) data.append('visa', files.visa)

  return data
}

/**
 * Отправка заявки. Пока заглушка.
 *
 * Подключение бекенда — замена тела на запрос с этим же `FormData`:
 * `const response = await fetch(endpoint, { method: 'POST', body: toFormData(payload) })`.
 * Сигнатура и формат ответа при этом не меняются.
 */
export async function submitApplication(payload: ApplicationPayload): Promise<SubmitResult> {
  toFormData(payload)
  await new Promise((resolve) => setTimeout(resolve, FAKE_LATENCY_MS))

  return { ok: true }
}
