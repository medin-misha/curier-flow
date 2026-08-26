import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { CourierResponse } from './api/couriers'
import App from './App.vue'

let wrapper: VueWrapper | undefined
let serverCouriers: CourierResponse[]
let hasRefreshSession: boolean
let failNextCourierRequest: boolean
let requests: Array<{ url: string; init: RequestInit }>

const admin = {
  id: 'admin-01',
  username: 'root.admin',
  telegram_id: null,
  is_active: true,
  created_at: '2026-08-01T10:00:00Z',
  updated_at: '2026-08-01T10:00:00Z',
}

function courier(index: number, fullName = `Курьер ${index}`): CourierResponse {
  const id = `00000000-0000-4000-8000-${String(index).padStart(12, '0')}`
  return {
    id,
    full_name: fullName,
    email: `courier${index}@example.com`,
    phone: `+4207000000${String(index).padStart(2, '0')}`,
    date_of_birth: '1992-05-12',
    city: index % 2 ? 'Прага' : 'Брно',
    address: 'Testovací 12',
    citizenship: 'Чехия',
    bank_account: 'CZ00 0000 0000',
    contact_platform: 'Telegram',
    contact: `@courier${index}`,
    source: 'Сайт MFS',
    consent_to_processing: true,
    consent_at: '2026-08-20T09:00:00Z',
    platform_accounts: [
      {
        id: `platform-${index}`,
        courier_id: id,
        platform: index % 2 ? 'wolt' : 'foodora',
        status: index === 1 ? 'active' : 'pending',
        created_at: '2026-08-20T09:00:00Z',
        updated_at: '2026-08-20T09:00:00Z',
      },
    ],
    documents:
      index === 1
        ? [
            {
              id: 'document-1',
              courier_id: id,
              file_id: 'file-1',
              type: 'passport',
              purpose: 'platform_onboarding',
              legal_hold_until: null,
              file: {
                id: 'file-1',
                original_name: 'passport_scan.pdf',
                content_type: 'application/pdf',
                size: 1024,
                status: 'ready',
                etag: null,
                owner_id: id,
                created_at: '2026-08-20T09:00:00Z',
              },
              created_at: '2026-08-20T09:00:00Z',
              updated_at: '2026-08-20T09:00:00Z',
            },
          ]
        : [],
    created_at: `2026-08-${String(20 - index).padStart(2, '0')}T09:00:00Z`,
    updated_at: '2026-08-26T09:00:00Z',
  }
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: status === 204 ? undefined : { 'Content-Type': 'application/json' },
  })
}

function problem(status: number, detail: string) {
  return jsonResponse({ status, title: 'Unauthorized', detail }, status)
}

const fetchMock = vi.fn(async (input: string | URL | Request, init: RequestInit = {}) => {
  const rawUrl = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
  const url = new URL(rawUrl, 'http://frontend.test')
  const method = init.method || 'GET'
  requests.push({ url: `${url.pathname}${url.search}`, init })

  if (url.pathname === '/admin/auth/refresh') {
    return hasRefreshSession
      ? jsonResponse({ access_token: 'access-token', token_type: 'bearer', expires_in: 900 })
      : problem(401, 'Refresh token is required')
  }
  if (url.pathname === '/admin/auth/login') {
    hasRefreshSession = true
    return jsonResponse({ access_token: 'login-token', token_type: 'bearer', expires_in: 900 })
  }
  if (url.pathname === '/admin/auth/logout') {
    hasRefreshSession = false
    return jsonResponse(null, 204)
  }
  if (url.pathname === '/admin/admins/me') return jsonResponse(admin)

  if (url.pathname === '/files/file-1' && method === 'GET') {
    return jsonResponse({
      download_url: 'https://storage.test/passport_scan.pdf?signature=test',
    })
  }

  if (url.pathname.startsWith('/courier') && failNextCourierRequest) {
    failNextCourierRequest = false
    return problem(401, 'Access token expired')
  }

  if (url.pathname === '/courier' && method === 'GET') {
    const start = url.searchParams.get('cursor') === 'cursor-2' ? 5 : 0
    const items = serverCouriers.slice(start, start + 5)
    return jsonResponse({
      items,
      next_cursor: start === 0 && serverCouriers.length > 5 ? 'cursor-2' : null,
    })
  }
  if (url.pathname === '/courier' && method === 'POST') {
    const formData = init.body as FormData
    const payload = JSON.parse(String(formData.get('payload'))) as Record<string, unknown>
    const created = {
      ...courier(20, String(payload.full_name)),
      email: String(payload.email),
      phone: String(payload.phone),
      date_of_birth: String(payload.date_of_birth),
    }
    serverCouriers.unshift(created)
    return jsonResponse(created, 201)
  }

  const courierId = url.pathname.split('/')[2]
  const existing = serverCouriers.find((item) => item.id === courierId)
  if (!existing) return problem(404, 'Courier not found')
  if (method === 'GET') return jsonResponse(existing)
  if (method === 'PATCH') {
    const body = JSON.parse(String(init.body)) as Record<string, unknown>
    const updated = {
      ...existing,
      full_name: String(body.full_name),
      email: String(body.email),
      phone: String(body.phone),
      updated_at: '2026-08-27T09:00:00Z',
    }
    serverCouriers[serverCouriers.indexOf(existing)] = updated
    return jsonResponse(updated)
  }
  if (method === 'DELETE') {
    serverCouriers = serverCouriers.filter((item) => item.id !== courierId)
    return jsonResponse(null, 204)
  }
  return problem(405, 'Method not allowed')
})

async function mountApp() {
  wrapper = mount(App, {
    global: {
      stubs: {
        Teleport: true,
      },
    },
  })
  await flushPromises()
  await flushPromises()
  return wrapper
}

function buttonWithText(page: VueWrapper, text: string) {
  const button = page.findAll('button').find((item) => item.text().trim() === text)
  if (!button) throw new Error(`Кнопка «${text}» не найдена`)
  return button
}

beforeEach(() => {
  serverCouriers = Array.from({ length: 6 }, (_, index) => courier(index + 1))
  hasRefreshSession = true
  failNextCourierRequest = false
  requests = []
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockClear()
})

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  document.body.innerHTML = ''
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('аутентификация администратора', () => {
  it('показывает вход без refresh-сессии и позволяет войти и выйти', async () => {
    hasRefreshSession = false
    const page = await mountApp()

    expect(page.get('#loginTitle').text()).toBe('Вход в панель')
    await page.get('#username').setValue('root.admin')
    await page.get('#password').setValue('correct-password')
    await page.get('.auth-form').trigger('submit')
    await flushPromises()
    await flushPromises()

    expect(page.get('[data-od-id="couriers-title"]').text()).toBe('Курьеры')
    const loginRequest = requests.find((request) => request.url === '/admin/auth/login')
    expect(JSON.parse(String(loginRequest?.init.body))).toEqual({
      username: 'root.admin',
      password: 'correct-password',
    })

    await page.get('[aria-label="Выйти из панели"]').trigger('click')
    await flushPromises()
    expect(page.find('#loginTitle').exists()).toBe(true)
    expect(requests.some((request) => request.url === '/admin/auth/logout')).toBe(true)
  })

  it('обновляет access-токен после 401 и загружает cursor-страницы', async () => {
    failNextCourierRequest = true
    const page = await mountApp()

    expect(page.findAll('tbody tr')).toHaveLength(5)
    expect(page.get('.pagination-summary').text()).toBe('Страница 1 · записей 5')
    expect(requests.filter((request) => request.url === '/admin/auth/refresh')).toHaveLength(2)
    const courierRequest = requests.find((request) => request.url.startsWith('/courier?'))
    expect(new Headers(courierRequest?.init.headers).get('Authorization')).toBe(
      'Bearer access-token',
    )

    await page.get('[aria-label="Следующая страница"]').trigger('click')
    await flushPromises()

    expect(page.findAll('tbody tr')).toHaveLength(1)
    expect(page.get('.pagination-summary').text()).toBe('Страница 2 · записей 1')
    expect(requests.some((request) => request.url.includes('cursor=cursor-2'))).toBe(true)
  })
})

describe('Courier CRUD', () => {
  it('создаёт курьера multipart-запросом и обновляет реестр', async () => {
    const page = await mountApp()

    await buttonWithText(page, 'Создать').trigger('click')
    await page.get('#fullName').setValue('Ирина Тестова')
    await page.get('#birthDate').setValue('1991-05-12')
    await page.get('#email').setValue('irina@example.com')
    await page.get('#phone').setValue('+420700000099')
    await page.get('[data-od-id="create-courier-dialog"] form').trigger('submit')
    await flushPromises()
    await flushPromises()

    const request = requests.find(
      (item) => item.url === '/courier' && item.init.method === 'POST',
    )
    const formData = request?.init.body as FormData
    const payload = JSON.parse(String(formData.get('payload')))
    expect(payload.platform_accounts).toEqual([{ platform: 'wolt' }])
    expect(payload.documents).toEqual([])
    expect(page.text()).toContain('Ирина Тестова')
    expect(page.get('[role="status"]').text()).toContain('Курьер сохранён')
  })

  it('читает, редактирует и удаляет профиль курьера', async () => {
    const page = await mountApp()

    await page.get('.table-action').trigger('click')
    await flushPromises()
    expect(page.get('[data-od-id="courier-detail-dialog"]').text()).toContain(
      'passport_scan.pdf',
    )

    let downloadedHref = ''
    let downloadedName = ''
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      downloadedHref = this.href
      downloadedName = this.download
    })
    await buttonWithText(page, 'Скачать').trigger('click')
    await flushPromises()

    expect(requests.some((request) => request.url === '/files/file-1')).toBe(true)
    expect(downloadedHref).toBe('https://storage.test/passport_scan.pdf?signature=test')
    expect(downloadedName).toBe('passport_scan.pdf')

    await buttonWithText(page, 'Редактировать').trigger('click')
    await page.get('#edit-fullName').setValue('Курьер Обновлён')
    await page.get('[data-od-id="edit-courier-dialog"] form').trigger('submit')
    await flushPromises()

    expect(page.get('[data-od-id="courier-detail-dialog"]').text()).toContain(
      'Курьер Обновлён',
    )
    expect(
      requests.some((request) => request.init.method === 'PATCH'),
    ).toBe(true)

    await buttonWithText(page, 'Удалить').trigger('click')
    await page.get('[data-od-id="delete-courier-dialog"] .btn-danger').trigger('click')
    await flushPromises()
    await flushPromises()

    expect(page.find('[role="dialog"]').exists()).toBe(false)
    expect(requests.some((request) => request.init.method === 'DELETE')).toBe(true)
    expect(page.get('[role="status"]').text()).toContain('Курьер удалён')
  })
})
