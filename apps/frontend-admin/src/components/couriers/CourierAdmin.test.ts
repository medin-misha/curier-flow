import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { configureAccessRecovery, setAccessToken, type ApiProblem } from '../../api/client'
import type { CourierResponse } from '../../api/couriers'
import type { CourierBulkStatusInput } from '../../types/courier'
import CourierAdmin from './CourierAdmin.vue'
import CourierBulkModal from './CourierBulkModal.vue'

let wrapper: VueWrapper | undefined
let couriers: CourierResponse[]
let nextProblem: ApiProblem | null
let loseBulkResponse: boolean
let failList: boolean
let bulkGate: Promise<void> | null
let commands: Array<{ path: string; init: RequestInit; body: { courier_ids: string[] } & Partial<CourierBulkStatusInput> }>
let listQueries: URLSearchParams[]
let savedResults: Map<string, unknown>

function courier(index: number): CourierResponse {
  const id = `00000000-0000-4000-8000-${String(index).padStart(12, '0')}`
  return {
    id, full_name: `Курьер ${index}`, email: `courier${index}@example.com`,
    phone: `+420700000${String(index).padStart(3, '0')}`, date_of_birth: '1992-05-12',
    city: 'Прага', address: null, citizenship: null, bank_account: null,
    contact_platform: null, contact: null, source: null,
    consent_to_processing: true, consent_at: null, documents: [],
    platform_accounts: [
      {
        id: `account-${index}`, courier_id: id, platform: index === 2 ? 'foodora' : 'wolt',
        status: index === 1 ? 'active' : 'pending',
        created_at: '2026-09-01T10:00:00Z', updated_at: '2026-09-01T10:00:00Z',
      },
      {
        id: `bolt-${index}`, courier_id: id, platform: 'bolt_food', status: 'pending',
        created_at: '2026-09-01T10:00:00Z', updated_at: '2026-09-01T10:00:00Z',
      },
    ],
    created_at: '2026-09-01T10:00:00Z', updated_at: '2026-09-01T10:00:00Z',
  }
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

const fetchMock = vi.fn(async (path: string, init: RequestInit = {}) => {
  const url = new URL(path, 'https://admin.test')
  if (url.pathname === '/courier') {
    listQueries.push(url.searchParams)
    if (failList) return json({ status: 503 }, 503)
    const status = url.searchParams.get('status')
    const name = url.searchParams.get('full_name')
    const filtered = couriers.filter((item) => (!status || item.platform_accounts.some((account) => account.status === status)) && (!name || item.full_name === name))
    const offset = Number(url.searchParams.get('cursor') || 0)
    const limit = Number(url.searchParams.get('limit'))
    return json({ items: filtered.slice(offset, offset + limit), next_cursor: offset + limit < filtered.length ? String(offset + limit) : null })
  }
  if (url.pathname === '/courier/bulk-delete' || url.pathname === '/courier/bulk-status') {
    const body = JSON.parse(String(init.body))
    commands.push({ path: url.pathname, init, body })
    if (bulkGate) await bulkGate
    if (nextProblem) {
      const problem = nextProblem
      nextProblem = null
      return json(problem, problem.status)
    }
    const key = new Headers(init.headers).get('Idempotency-Key')!
    if (savedResults.has(key)) return json(savedResults.get(key))
    const selected = couriers.filter((item) => body.courier_ids.includes(item.id))
    let result: unknown
    if (url.pathname.endsWith('bulk-delete')) {
      couriers = couriers.filter((item) => !body.courier_ids.includes(item.id))
      result = { deleted_count: selected.length }
    } else {
      let updated = 0
      for (const item of selected) {
        const account = item.platform_accounts.find((account) => account.platform === body.platform)!
        if (account.status !== body.status) {
          account.status = body.status
          updated += 1
        }
      }
      result = { updated_count: updated, unchanged_count: selected.length - updated }
    }
    savedResults.set(key, result)
    if (loseBulkResponse) {
      loseBulkResponse = false
      throw new TypeError('Failed to fetch')
    }
    return json(result)
  }
  throw new Error(`Неожиданный запрос: ${path}`)
})

async function mountRegistry() {
  wrapper = mount(CourierAdmin, { attachTo: document.body, global: { stubs: { Teleport: true } } })
  await flushPromises()
  return wrapper
}

function checkbox(page: VueWrapper, index: number) {
  return page.get<HTMLInputElement>(`[aria-label="Выбрать курьера Курьер ${index}"]`)
}

function pageCheckbox(page: VueWrapper) {
  return page.get<HTMLInputElement>('.courier-page-selection input')
}

function toolbarButton(page: VueWrapper, text: string) {
  const button = page.findAll('.courier-bulk-toolbar button').find((item) => item.text() === text)
  if (!button) throw new Error(`Кнопка «${text}» не найдена`)
  return button
}

async function openBulk(page: VueWrapper, action: 'delete' | 'status') {
  await toolbarButton(page, action === 'delete' ? 'Удалить выбранных' : 'Изменить статус').trigger('click')
  return page.getComponent(CourierBulkModal)
}

async function nextPage(page: VueWrapper) {
  await page.get('[aria-label="Следующая страница"]').trigger('click')
  await flushPromises()
}

beforeEach(() => {
  couriers = Array.from({ length: 6 }, (_, index) => courier(index + 1))
  nextProblem = null
  loseBulkResponse = false
  failList = false
  bulkGate = null
  commands = []
  listQueries = []
  savedResults = new Map()
  fetchMock.mockClear()
  vi.stubGlobal('fetch', fetchMock)
  setAccessToken('admin-token')
})

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  document.body.innerHTML = ''
  setAccessToken(null)
  configureAccessRecovery(null)
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('Массовые операции реестра курьеров', () => {
  it('выбирает строки без открытия профиля, сохраняет выбор между страницами и сбрасывает поиском', async () => {
    const page = await mountRegistry()
    await checkbox(page, 1).trigger('click')
    await checkbox(page, 1).trigger('keydown', { key: 'Enter' })
    await checkbox(page, 1).trigger('keydown', { key: ' ' })
    await checkbox(page, 1).setValue(true)
    expect(page.find('[role="dialog"]').exists()).toBe(false)
    expect(pageCheckbox(page).element.indeterminate).toBe(true)
    await pageCheckbox(page).setValue(true)
    expect(page.get('.courier-bulk-toolbar').text()).toContain('Выбрано: 5 / 100')
    await nextPage(page)
    expect(pageCheckbox(page).element.checked).toBe(false)
    await checkbox(page, 6).setValue(true)
    await page.get('[aria-label="Предыдущая страница"]').trigger('click')
    await flushPromises()
    expect(pageCheckbox(page).element.checked).toBe(true)
    await pageCheckbox(page).setValue(false)
    expect(page.get('.courier-bulk-toolbar').text()).toContain('Выбрано: 1 / 100')
    await page.get('[data-od-id="courier-search"]').setValue('Курьер 1')
    await page.get('[data-od-id="couriers-filters"]').trigger('submit')
    await flushPromises()
    expect(page.get('.courier-bulk-toolbar').text()).toContain('Выбрано: 0 / 100')
    expect(page.findAll('tbody tr')).toHaveLength(1)
    expect(commands).toHaveLength(0)
  })

  it('удаляет только подтверждённую выборку с разных страниц и начинает пагинацию заново', async () => {
    const page = await mountRegistry()
    await checkbox(page, 1).setValue(true)
    await nextPage(page)
    await checkbox(page, 6).setValue(true)
    let dialog = await openBulk(page, 'delete')
    expect(dialog.get('ul').text()).toContain('Курьер 1')
    expect(dialog.get('ul').text()).toContain('Курьер 6')
    await dialog.get('[aria-label="Закрыть"]').trigger('click')
    expect(commands).toHaveLength(0)
    expect(page.get('.courier-bulk-toolbar').text()).toContain('Выбрано: 2 / 100')
    dialog = await openBulk(page, 'delete')
    await dialog.get('form').trigger('submit')
    await flushPromises()
    expect(commands).toHaveLength(1)
    expect(commands[0].path).toBe('/courier/bulk-delete')
    expect(commands[0].init.method).toBe('POST')
    expect(commands[0].body).toEqual({ courier_ids: [courier(1).id, courier(6).id] })
    const headers = new Headers(commands[0].init.headers)
    expect(headers.get('Idempotency-Key')).toMatch(/^[\da-f-]{36}$/)
    expect(headers.get('Authorization')).toBe('Bearer admin-token')
    expect(headers.get('Content-Type')).toBe('application/json')
    expect(page.findAll('tbody tr')).toHaveLength(4)
    expect(page.get('.pagination-summary').text()).toContain('Страница 1')
    expect(listQueries.at(-1)?.has('cursor')).toBe(false)
    expect(page.get('[role="status"]').text()).toContain('Удалено профилей: 2')
    expect(page.get('.courier-bulk-toolbar').text()).toContain('Выбрано: 0 / 100')
    expect(page.find('[role="dialog"]').exists()).toBe(false)
    expect(document.body.classList.contains('modal-open')).toBe(false)
  })

  it('проверяет подключение платформы и показывает updated/unchanged из API', async () => {
    const page = await mountRegistry()
    await checkbox(page, 1).setValue(true)
    await checkbox(page, 2).setValue(true)
    let dialog = await openBulk(page, 'status')
    expect(dialog.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    await dialog.get('#courier-bulk-platform').setValue('wolt')
    await dialog.get('#courier-bulk-status').setValue('active')
    expect(dialog.get('[role="alert"]').text()).toContain('Курьер 2')
    await dialog.get('form').trigger('submit')
    expect(commands).toHaveLength(0)
    await dialog.get('[aria-label="Закрыть"]').trigger('click')
    await checkbox(page, 2).setValue(false)
    await checkbox(page, 3).setValue(true)
    dialog = await openBulk(page, 'status')
    await dialog.get('#courier-bulk-platform').setValue('wolt')
    await dialog.get('#courier-bulk-status').setValue('active')
    await dialog.get('form').trigger('submit')
    await flushPromises()
    expect(commands[0].path).toBe('/courier/bulk-status')
    expect(commands[0].init.method).toBe('PATCH')
    expect(commands[0].body).toEqual({ courier_ids: [courier(1).id, courier(3).id], platform: 'wolt', status: 'active' })
    expect(couriers[2].platform_accounts[1].status).toBe('pending')
    expect(page.get('[role="status"]').text()).toContain('Изменено: 1. Уже имели нужный статус: 1.')
  })

  it('повторяет потерянный ответ с прежним ключом, блокирует повторную отправку и закрытие во время запроса', async () => {
    const page = await mountRegistry()
    await checkbox(page, 1).setValue(true)
    const dialog = await openBulk(page, 'delete')
    let release!: () => void
    bulkGate = new Promise<void>((resolve) => { release = resolve })
    loseBulkResponse = true
    await dialog.get('form').trigger('submit')
    await dialog.get('form').trigger('submit')
    await dialog.get('[role="dialog"]').trigger('keydown', { key: 'Escape' })
    expect(commands).toHaveLength(1)
    expect(page.find('[role="dialog"]').exists()).toBe(true)
    expect(dialog.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    expect(page.emitted('busyChange')?.at(-1)).toEqual([true])
    release()
    await flushPromises()
    expect(dialog.get('[role="alert"]').text()).toContain('Повторите запрос')
    expect(page.get('.courier-bulk-toolbar').text()).toContain('Выбрано: 1 / 100')
    expect(page.findAll('tbody tr')).toHaveLength(5)
    await dialog.get('[aria-label="Закрыть"]').trigger('click')
    const retry = await openBulk(page, 'delete')
    await retry.get('form').trigger('submit')
    await flushPromises()
    expect(commands).toHaveLength(2)
    expect(commands[1].init.body).toBe(commands[0].init.body)
    expect(new Headers(commands[1].init.headers).get('Idempotency-Key')).toBe(new Headers(commands[0].init.headers).get('Idempotency-Key'))
    expect(couriers).toHaveLength(5)
    expect(page.get('[role="status"]').text()).toContain('Удалено профилей: 1')
    expect(page.emitted('busyChange')?.at(-1)).toEqual([false])
  })

  it.each([
    [404, undefined, 'больше не существуют'],
    [409, 'signed-contract-protects-rental', 'Ни один курьер не удалён'],
    [422, undefined, 'от 1 до 100'],
    [503, undefined, 'Сервис временно недоступен'],
  ])('сохраняет выбор при ошибке %s %s', async (status, reason, message) => {
    const page = await mountRegistry()
    await checkbox(page, 1).setValue(true)
    nextProblem = { status, reason, courier_id: courier(1).id }
    const dialog = await openBulk(page, 'delete')
    await dialog.get('form').trigger('submit')
    await flushPromises()
    expect(dialog.get('[role="alert"]').text()).toContain(message)
    if (status === 404 || status === 409) expect(dialog.get('[role="alert"]').text()).toContain('Курьер 1')
    expect(couriers).toHaveLength(6)
    expect(page.get('.courier-bulk-toolbar').text()).toContain('Выбрано: 1 / 100')
  })

  it('обрабатывает серверный конфликт платформы и выдаёт новый ключ изменённым параметрам', async () => {
    const page = await mountRegistry()
    await checkbox(page, 1).setValue(true)
    const dialog = await openBulk(page, 'status')
    await dialog.get('#courier-bulk-platform').setValue('wolt')
    await dialog.get('#courier-bulk-status').setValue('inactive')
    nextProblem = { status: 409, reason: 'platform-account-missing', platform: 'wolt', courier_ids: [courier(1).id] }
    await dialog.get('form').trigger('submit')
    await flushPromises()
    expect(dialog.get('[role="alert"]').text()).toContain('Статусы всей выборки остались прежними')
    expect(dialog.get('[role="alert"]').text()).toContain('Курьер 1')
    await dialog.get('#courier-bulk-platform').setValue('bolt_food')
    expect(dialog.find('[role="alert"]').exists()).toBe(false)
    await dialog.get('form').trigger('submit')
    await flushPromises()
    expect(new Headers(commands[1].init.headers).get('Idempotency-Key')).not.toBe(new Headers(commands[0].init.headers).get('Idempotency-Key'))
  })

  it('обновляет фильтрованный реестр после смены статуса', async () => {
    const page = await mountRegistry()
    await page.get('[data-od-id="courier-status-filter"]').setValue('active')
    await page.get('[data-od-id="couriers-filters"]').trigger('submit')
    await flushPromises()
    await pageCheckbox(page).setValue(true)
    const dialog = await openBulk(page, 'status')
    await dialog.get('#courier-bulk-platform').setValue('wolt')
    await dialog.get('#courier-bulk-status').setValue('inactive')
    await dialog.get('form').trigger('submit')
    await flushPromises()
    expect(listQueries.at(-1)?.get('status')).toBe('active')
    expect(page.findAll('tbody tr')).toHaveLength(0)
    expect(page.text()).toContain('Ничего не найдено')
    expect(page.get('.courier-bulk-toolbar').text()).toContain('Выбрано: 0 / 100')
  })

  it('отделяет ошибку обновления реестра от успешного удаления', async () => {
    const page = await mountRegistry()
    await pageCheckbox(page).setValue(true)
    const dialog = await openBulk(page, 'delete')
    failList = true
    await dialog.get('form').trigger('submit')
    await flushPromises()
    expect(page.find('[role="dialog"]').exists()).toBe(false)
    expect(page.get('[role="alert"]').text()).toContain('Не удалось загрузить реестр')
    expect(page.get('[role="status"]').text()).toContain('Удалено профилей: 5')
    expect(page.findAll('tbody tr')).toHaveLength(0)
    failList = false
    await page.get('.registry-error button').trigger('click')
    await flushPromises()
    expect(page.findAll('tbody tr')).toHaveLength(1)
    expect(commands).toHaveLength(1)
  })

  it('ограничивает выбор сотней курьеров, сохраняя возможность снять отметки', async () => {
    couriers = Array.from({ length: 105 }, (_, index) => courier(index + 1))
    const page = await mountRegistry()
    for (let index = 0; index < 20; index += 1) {
      await pageCheckbox(page).setValue(true)
      await nextPage(page)
    }
    expect(page.get('.courier-bulk-toolbar').text()).toContain('Выбрано: 100 / 100')
    expect(pageCheckbox(page).element.disabled).toBe(true)
    expect(checkbox(page, 101).element.disabled).toBe(true)
    await page.get('[aria-label="Предыдущая страница"]').trigger('click')
    await flushPromises()
    expect(checkbox(page, 100).element.disabled).toBe(false)
    await checkbox(page, 100).setValue(false)
    await nextPage(page)
    expect(pageCheckbox(page).element.disabled).toBe(true)
    expect(checkbox(page, 101).element.disabled).toBe(false)
    await checkbox(page, 101).setValue(true)
    const dialog = await openBulk(page, 'delete')
    await dialog.get('form').trigger('submit')
    await flushPromises()
    expect(commands[0].body.courier_ids).toHaveLength(100)
    expect(new Set(commands[0].body.courier_ids).size).toBe(100)
    expect(commands[0].body.courier_ids).not.toContain(courier(100).id)
    expect(commands[0].body.courier_ids).toContain(courier(101).id)
  }, 20_000)
})
