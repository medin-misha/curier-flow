export interface ApiProblem {
  type?: string
  title?: string
  status?: number
  detail?: string
  instance?: string
  request_id?: string
  reason?: string
  field?: string
  errors?: Array<{
    loc: Array<string | number>
    msg: string
    type: string
  }>
}

export class ApiError extends Error {
  readonly status: number
  readonly problem: ApiProblem | null

  constructor(status: number, problem: ApiProblem | null) {
    super(problem?.detail || problem?.title || `HTTP ${status}`)
    this.name = 'ApiError'
    this.status = status
    this.problem = problem
  }
}

interface ApiRequestOptions extends RequestInit {
  auth?: boolean
  retryAuth?: boolean
}

const apiBaseUrl = (import.meta.env.VITE_API_URL || '').replace(/\/+$/, '')

let accessToken: string | null = null
let recoverAccess: (() => Promise<boolean>) | null = null
let recoveryPromise: Promise<boolean> | null = null

export function setAccessToken(token: string | null) {
  accessToken = token
}

export function configureAccessRecovery(handler: (() => Promise<boolean>) | null) {
  recoverAccess = handler
}

async function recoverOnce() {
  if (!recoverAccess) return false
  if (!recoveryPromise) {
    recoveryPromise = recoverAccess().finally(() => {
      recoveryPromise = null
    })
  }
  return recoveryPromise
}

async function problemFrom(response: Response): Promise<ApiProblem | null> {
  try {
    return (await response.json()) as ApiProblem
  } catch {
    return null
  }
}

export async function apiRequest<T>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  const headers = new Headers(options.headers)
  if (options.auth !== false && accessToken) {
    headers.set('Authorization', `Bearer ${accessToken}`)
  }

  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...options,
    headers,
    credentials: 'include',
  })

  if (
    response.status === 401 &&
    options.auth !== false &&
    options.retryAuth !== false &&
    (await recoverOnce())
  ) {
    return apiRequest<T>(path, { ...options, retryAuth: false })
  }

  if (!response.ok) {
    throw new ApiError(response.status, await problemFrom(response))
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export function jsonBody(value: unknown): Pick<RequestInit, 'body' | 'headers'> {
  return {
    body: JSON.stringify(value),
    headers: {
      'Content-Type': 'application/json',
    },
  }
}

export function apiErrorMessage(error: unknown, fallback: string) {
  if (error instanceof ApiError) {
    if (error.status === 409) return 'Такая запись уже существует или конфликтует с другой.'
    if (error.status === 422) return 'Проверьте значения полей формы.'
    if (error.status >= 500) return 'Сервис временно недоступен. Попробуйте ещё раз.'
    return error.problem?.detail || fallback
  }
  return fallback
}
