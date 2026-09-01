import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AdminResponse } from './api/admins'
import type { CourierResponse } from './api/couriers'
import type { PlatformStatus } from './types/courier'
import App from './App.vue'

let wrapper: VueWrapper | undefined
let serverAdmins: AdminResponse[]
let serverCouriers: CourierResponse[]
let serverTransports: TestTransport[]
let serverRentals: TestRental[]
let serverReceipts: TestReceipt[]
let serverReceiptFiles: Record<string, TestStoredFile>
let receiptUploadIndex: number
let hasRefreshSession: boolean
let failNextCourierRequest: boolean
let requests: Array<{ url: string; init: RequestInit }>

const currentAdminId = '10000000-0000-4000-8000-000000000001'

interface TestComponent {
  id: string
  transport_id: string
  name: string
  unit_price: string
  quantity: number
  total_price: string
  created_at: string
  updated_at: string
}

interface TestFile {
  id: string
  original_name: string
  content_type: string
  size: number
  status: string
  created_at: string
}

interface TestRental {
  id: string
  transport_id: string
  courier_id: string
  started_at: string
  ended_at: string | null
  file_id: string | null
  file: TestFile | null
  is_active: boolean
  created_at: string
  updated_at: string
}

interface TestTransport {
  id: string
  type: string
  model: string
  serial_number: string
  color: string
  deposit_required: boolean
  deposit_amount: string | null
  rental_price: string
  is_available: boolean
  components: TestComponent[]
  active_rental: TestRental | null
  created_at: string
  updated_at: string
}

interface TestReceipt {
  id: string
  file_id: string
  amount: string
  date: string
  created_at: string
  updated_at: string
}

interface TestStoredFile {
  id: string
  original_name: string
  content_type: string
  size: number
  status: string
  etag: string | null
  owner_id: string | null
  created_at: string
  download_url: string | null
}

function bike(index: number): TestTransport {
  return {
    id: `20000000-0000-4000-8000-${String(index).padStart(12, '0')}`,
    type: 'e-bike',
    model: `City Runner ${index}`,
    serial_number: `BIKE-${String(index).padStart(3, '0')}`,
    color: index % 2 ? 'Black' : 'Blue',
    deposit_required: true,
    deposit_amount: '500.00',
    rental_price: '1250.00',
    is_available: true,
    components: [],
    active_rental: null,
    created_at: '2026-08-10T10:00:00Z',
    updated_at: '2026-08-20T10:00:00Z',
  }
}

function receipt(index: number, amount: string, date: string, createdAt: string): TestReceipt {
  return {
    id: `30000000-0000-4000-8000-${String(index).padStart(12, '0')}`,
    file_id: `receipt-file-${index}`,
    amount,
    date,
    created_at: createdAt,
    updated_at: createdAt,
  }
}

function receiptFile(item: TestReceipt): TestStoredFile {
  return {
    id: item.file_id,
    original_name: `receipt-${item.id.slice(-2)}.pdf`,
    content_type: 'application/pdf',
    size: 2048,
    status: 'ready',
    etag: `etag-${item.file_id}`,
    owner_id: null,
    created_at: item.created_at,
    download_url: `https://storage.test/download/${item.file_id}.pdf`,
  }
}

function adminRecord(
  index: number,
  username = index === 1 ? 'root.admin' : `operator.${index}`,
  isActive = true,
): AdminResponse {
  return {
    id: `10000000-0000-4000-8000-${String(index).padStart(12, '0')}`,
    username,
    telegram_id: index === 1 ? null : 700_000 + index,
    is_active: isActive,
    created_at: `2026-08-${String(10 - index).padStart(2, '0')}T10:00:00Z`,
    updated_at: '2026-08-20T10:00:00Z',
  }
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

function problem(status: number, detail: string, reason?: string) {
  return jsonResponse({ status, title: 'Error', detail, reason }, status)
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
  if (url.pathname === '/admin/admins/me') {
    return jsonResponse(serverAdmins.find((item) => item.id === currentAdminId))
  }

  if (url.pathname === '/admin/admins' && method === 'GET') {
    const start = url.searchParams.get('cursor') === 'admin-cursor-2' ? 5 : 0
    const items = serverAdmins.slice(start, start + 5)
    return jsonResponse({
      items,
      next_cursor: start === 0 && serverAdmins.length > 5 ? 'admin-cursor-2' : null,
    })
  }
  if (url.pathname === '/admin/admins' && method === 'POST') {
    const body = JSON.parse(String(init.body)) as {
      username: string
      password: string
      telegram_id: number | null
    }
    if (serverAdmins.some((item) => item.username === body.username)) {
      return problem(409, 'Duplicate admin', 'duplicate-admin')
    }
    const created: AdminResponse = {
      id: '10000000-0000-4000-8000-000000000099',
      username: body.username,
      telegram_id: body.telegram_id,
      is_active: true,
      created_at: '2026-08-28T10:00:00Z',
      updated_at: '2026-08-28T10:00:00Z',
    }
    serverAdmins.unshift(created)
    return jsonResponse(created, 201)
  }

  if (url.pathname.startsWith('/admin/admins/')) {
    const pathParts = url.pathname.split('/')
    const adminId = pathParts[3]
    const action = pathParts[4]
    const existingAdmin = serverAdmins.find((item) => item.id === adminId)
    if (!existingAdmin) return problem(404, 'Admin not found')

    if (method === 'GET' && !action) return jsonResponse(existingAdmin)
    if (method === 'PATCH' && !action) {
      const body = JSON.parse(String(init.body)) as {
        username?: string
        telegram_id?: number | null
      }
      if (
        body.username &&
        serverAdmins.some((item) => item.id !== adminId && item.username === body.username)
      ) {
        return problem(409, 'Duplicate admin', 'duplicate-admin')
      }
      if (body.username !== undefined) existingAdmin.username = body.username
      if (body.telegram_id !== undefined) existingAdmin.telegram_id = body.telegram_id
      existingAdmin.updated_at = '2026-08-28T11:00:00Z'
      return jsonResponse(existingAdmin)
    }
    if (method === 'POST' && action === 'deactivate') {
      if (adminId === currentAdminId) {
        return problem(409, 'An admin cannot deactivate itself', 'self-deactivation')
      }
      existingAdmin.is_active = false
      existingAdmin.updated_at = '2026-08-28T12:00:00Z'
      return jsonResponse(existingAdmin)
    }
    if (method === 'POST' && action === 'activate') {
      existingAdmin.is_active = true
      existingAdmin.updated_at = '2026-08-28T12:30:00Z'
      return jsonResponse(existingAdmin)
    }
    if (method === 'POST' && action === 'reset-password') return jsonResponse(null, 204)
  }

  if (url.pathname === '/receipts' && method === 'GET') {
    const cursor = url.searchParams.get('cursor')
    const start = cursor ? Number(cursor.replace('receipt-cursor-', '')) : 0
    const requestedLimit = Number(url.searchParams.get('limit') || 50)
    const pageSize = requestedLimit === 200 ? 3 : requestedLimit
    const items = serverReceipts.slice(start, start + pageSize)
    const next = start + items.length
    return jsonResponse({
      items,
      next_cursor: next < serverReceipts.length ? `receipt-cursor-${next}` : null,
    })
  }
  if (url.pathname === '/receipts' && method === 'POST') {
    const body = JSON.parse(String(init.body)) as { file_id: string; amount: string; date: string }
    if (!serverReceiptFiles[body.file_id] || serverReceiptFiles[body.file_id].status !== 'ready') {
      return problem(422, 'Receipt file is not ready', 'file-not-ready')
    }
    if (serverReceipts.some((item) => item.file_id === body.file_id)) {
      return problem(409, 'File is already attached', 'receipt-file-in-use')
    }
    const created: TestReceipt = {
      id: '30000000-0000-4000-8000-000000000099',
      file_id: body.file_id,
      amount: body.amount,
      date: body.date,
      created_at: '2026-08-30T12:00:00Z',
      updated_at: '2026-08-30T12:00:00Z',
    }
    serverReceipts.unshift(created)
    return jsonResponse(created, 201)
  }
  if (url.pathname.startsWith('/receipts/')) {
    const receiptId = url.pathname.split('/')[2]
    const existingReceipt = serverReceipts.find((item) => item.id === receiptId)
    if (!existingReceipt) return problem(404, 'Receipt not found')
    if (method === 'GET') return jsonResponse(existingReceipt)
    if (method === 'PATCH') {
      const body = JSON.parse(String(init.body)) as {
        file_id?: string
        amount?: string
        date?: string
      }
      if (body.file_id !== undefined) existingReceipt.file_id = body.file_id
      if (body.amount !== undefined) existingReceipt.amount = body.amount
      if (body.date !== undefined) existingReceipt.date = body.date
      existingReceipt.updated_at = '2026-08-30T13:00:00Z'
      return jsonResponse(existingReceipt)
    }
    if (method === 'DELETE') {
      serverReceipts = serverReceipts.filter((item) => item.id !== receiptId)
      return jsonResponse(null, 204)
    }
  }

  if (url.pathname === '/transport' && method === 'GET') {
    let items = [...serverTransports]
    const type = url.searchParams.get('type')
    const serial = url.searchParams.get('serial_number')
    const available = url.searchParams.get('is_available')
    const courierId = url.searchParams.get('courier_id')
    if (type) items = items.filter((item) => item.type === type)
    if (serial) items = items.filter((item) => item.serial_number === serial)
    if (available !== null) items = items.filter((item) => item.is_available === (available === 'true'))
    if (courierId) items = items.filter((item) => item.active_rental?.courier_id === courierId)
    return jsonResponse({ items: items.slice(0, 5), next_cursor: null })
  }
  if (url.pathname === '/transport' && method === 'POST') {
    const body = JSON.parse(String(init.body)) as Record<string, unknown>
    if (serverTransports.some((item) => item.serial_number === body.serial_number)) {
      return problem(409, 'Duplicate serial', 'duplicate-serial-number')
    }
    const created: TestTransport = {
      id: '20000000-0000-4000-8000-000000000099',
      type: String(body.type),
      model: String(body.model),
      serial_number: String(body.serial_number),
      color: String(body.color),
      deposit_required: Boolean(body.deposit_required),
      deposit_amount: body.deposit_amount === null ? null : String(body.deposit_amount),
      rental_price: String(body.rental_price),
      is_available: true,
      components: [],
      active_rental: null,
      created_at: '2026-08-28T10:00:00Z',
      updated_at: '2026-08-28T10:00:00Z',
    }
    serverTransports.unshift(created)
    return jsonResponse(created, 201)
  }
  if (url.pathname.startsWith('/transport/')) {
    const pathParts = url.pathname.split('/')
    const transportId = pathParts[2]
    const resource = pathParts[3]
    const childId = pathParts[4]
    const command = pathParts[5]
    const transport = serverTransports.find((item) => item.id === transportId)
    if (!transport) return problem(404, 'Transport not found')

    if (!resource && method === 'GET') return jsonResponse(transport)
    if (!resource && method === 'PATCH') {
      const body = JSON.parse(String(init.body)) as Record<string, unknown>
      if (body.type !== undefined) transport.type = String(body.type)
      if (body.model !== undefined) transport.model = String(body.model)
      if (body.serial_number !== undefined) transport.serial_number = String(body.serial_number)
      if (body.color !== undefined) transport.color = String(body.color)
      if (body.deposit_required !== undefined) {
        transport.deposit_required = Boolean(body.deposit_required)
        if (!transport.deposit_required) transport.deposit_amount = null
      }
      if (body.deposit_amount !== undefined) transport.deposit_amount = String(body.deposit_amount)
      if (body.rental_price !== undefined) transport.rental_price = String(body.rental_price)
      transport.updated_at = '2026-08-28T11:00:00Z'
      return jsonResponse(transport)
    }
    if (!resource && method === 'DELETE') {
      if (serverRentals.some((rental) => rental.transport_id === transportId && rental.file_id)) {
        return problem(409, 'Signed contract', 'signed-contract-protects-rental')
      }
      serverTransports = serverTransports.filter((item) => item.id !== transportId)
      serverRentals = serverRentals.filter((rental) => rental.transport_id !== transportId)
      return jsonResponse(null, 204)
    }

    if (resource === 'components' && !childId && method === 'POST') {
      const body = JSON.parse(String(init.body)) as { name: string; unit_price: string; quantity: number }
      const component: TestComponent = {
        id: 'component-transport-1',
        transport_id: transportId,
        name: body.name,
        unit_price: body.unit_price,
        quantity: body.quantity,
        total_price: (Number(body.unit_price) * body.quantity).toFixed(2),
        created_at: '2026-08-28T10:00:00Z',
        updated_at: '2026-08-28T10:00:00Z',
      }
      transport.components.push(component)
      return jsonResponse(component, 201)
    }
    if (resource === 'components' && childId) {
      const component = transport.components.find((item) => item.id === childId)
      if (!component) return problem(404, 'Component not found')
      if (method === 'PATCH') {
        const body = JSON.parse(String(init.body)) as { name: string; unit_price: string; quantity: number }
        Object.assign(component, {
          name: body.name,
          unit_price: body.unit_price,
          quantity: body.quantity,
          total_price: (Number(body.unit_price) * body.quantity).toFixed(2),
        })
        return jsonResponse(component)
      }
      if (method === 'DELETE') {
        transport.components = transport.components.filter((item) => item.id !== childId)
        return jsonResponse(null, 204)
      }
    }

    if (resource === 'rentals' && !childId && method === 'GET') {
      return jsonResponse({
        items: serverRentals.filter((rental) => rental.transport_id === transportId),
        next_cursor: null,
      })
    }
    if (resource === 'rentals' && !childId && method === 'POST') {
      const body = JSON.parse(String(init.body)) as {
        courier_id: string
        started_at: string
        ended_at: string | null
      }
      const rental: TestRental = {
        id: 'rental-transport-1',
        transport_id: transportId,
        courier_id: body.courier_id,
        started_at: body.started_at,
        ended_at: body.ended_at,
        file_id: null,
        file: null,
        is_active: body.ended_at === null,
        created_at: '2026-08-28T10:00:00Z',
        updated_at: '2026-08-28T10:00:00Z',
      }
      serverRentals.unshift(rental)
      if (rental.is_active) {
        transport.active_rental = rental
        transport.is_available = false
      }
      return jsonResponse(rental, 201)
    }
    if (resource === 'rentals' && childId) {
      const rental = serverRentals.find(
        (item) => item.id === childId && item.transport_id === transportId,
      )
      if (!rental) return problem(404, 'Rental not found')
      if (!command && method === 'GET') return jsonResponse(rental)
      if (command === 'close' && method === 'POST') {
        const body = JSON.parse(String(init.body)) as { ended_at: string }
        rental.ended_at = body.ended_at
        rental.is_active = false
        transport.active_rental = null
        transport.is_available = true
        return jsonResponse(rental)
      }
      if (command === 'contract' && method === 'POST') {
        rental.file_id = 'contract-file'
        rental.file = {
          id: 'contract-file',
          original_name: 'contract.pdf',
          content_type: 'application/pdf',
          size: 2048,
          status: 'ready',
          created_at: '2026-08-28T10:00:00Z',
        }
        return jsonResponse(rental)
      }
    }
  }

  if (url.pathname === '/files/upload-url' && method === 'POST') {
    const body = JSON.parse(String(init.body)) as {
      original_name: string
      content_type: string
      size: number
    }
    if (body.original_name !== 'contract.pdf') {
      receiptUploadIndex += 1
      const fileId = `receipt-upload-file-${receiptUploadIndex}`
      serverReceiptFiles[fileId] = {
        id: fileId,
        original_name: body.original_name,
        content_type: body.content_type,
        size: body.size,
        status: 'pending',
        etag: null,
        owner_id: null,
        created_at: '2026-08-30T12:00:00Z',
        download_url: null,
      }
      return jsonResponse({
        file_id: fileId,
        upload_url: `https://storage.test/upload/${fileId}`,
        content_type: body.content_type,
        expires_in: 900,
      }, 201)
    }
    return jsonResponse({
      file_id: 'contract-file',
      upload_url: 'https://storage.test/upload/contract',
      content_type: 'application/pdf',
      expires_in: 900,
    }, 201)
  }
  if (url.hostname === 'storage.test' && url.pathname === '/upload/contract' && method === 'PUT') {
    return new Response(null, { status: 200, headers: { ETag: '"contract-etag"' } })
  }
  if (url.hostname === 'storage.test' && url.pathname.startsWith('/upload/receipt-upload-file-') && method === 'PUT') {
    return new Response(null, { status: 200, headers: { ETag: '"receipt-etag"' } })
  }
  if (url.pathname === '/files/contract-file/confirm' && method === 'POST') {
    return jsonResponse({ id: 'contract-file', status: 'ready' })
  }
  if (url.pathname === '/files/contract-file' && method === 'GET') {
    return jsonResponse({ download_url: 'https://storage.test/download/contract.pdf' })
  }
  if (url.pathname === '/files/contract-file' && method === 'DELETE') return jsonResponse(null, 204)

  if (url.pathname === '/files/file-1' && method === 'GET') {
    return jsonResponse({
      download_url: 'https://storage.test/passport_scan.pdf?signature=test',
    })
  }
  if (url.hostname === 'storage.test' && url.pathname === '/passport_scan.pdf' && method === 'GET') {
    return new Response(new Blob(['photo'], { type: 'image/jpeg' }), { status: 200 })
  }

  if (url.pathname.startsWith('/files/')) {
    const pathParts = url.pathname.split('/')
    const fileId = pathParts[2]
    const action = pathParts[3]
    const file = serverReceiptFiles[fileId]
    if (!file) return problem(404, 'File not found')
    if (action === 'confirm' && method === 'POST') {
      file.status = 'ready'
      file.etag = 'receipt-etag'
      file.download_url = `https://storage.test/download/${file.id}`
      return jsonResponse(file)
    }
    if (!action && method === 'GET') return jsonResponse(file)
    if (!action && method === 'DELETE') {
      delete serverReceiptFiles[fileId]
      return jsonResponse(null, 204)
    }
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

  const pathParts = url.pathname.split('/')
  const courierId = pathParts[2]
  const existing = serverCouriers.find((item) => item.id === courierId)
  if (!existing) return problem(404, 'Courier not found')
  if (pathParts[3] === 'platform-accounts' && method === 'PATCH') {
    const account = existing.platform_accounts.find((item) => item.id === pathParts[4])
    if (!account) return problem(404, 'CourierPlatformAccount not found')

    const body = JSON.parse(String(init.body)) as { status: PlatformStatus }
    account.status = body.status
    account.updated_at = '2026-08-27T09:00:00Z'
    return jsonResponse(account)
  }
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

async function openAdminsTab(page: VueWrapper) {
  await page.get('[data-od-id="tab-admins"]').trigger('click')
  await flushPromises()
  await flushPromises()
}

async function openBikesTab(page: VueWrapper) {
  await page.get('[data-od-id="tab-bikes"]').trigger('click')
  await flushPromises()
  await flushPromises()
}

async function openFinanceTab(page: VueWrapper) {
  await page.get('[data-od-id="tab-finance"]').trigger('click')
  await flushPromises()
  await flushPromises()
}

beforeEach(() => {
  const localValues = new Map<string, string>()
  Object.defineProperty(window, 'localStorage', {
    configurable: true,
    value: {
      getItem: (key: string) => localValues.get(key) ?? null,
      setItem: (key: string, value: string) => localValues.set(key, value),
      removeItem: (key: string) => localValues.delete(key),
    },
  })
  serverAdmins = Array.from({ length: 6 }, (_, index) =>
    adminRecord(index + 1, undefined, index !== 4),
  )
  serverCouriers = Array.from({ length: 6 }, (_, index) => courier(index + 1))
  serverTransports = [bike(1), bike(2)]
  serverRentals = []
  serverReceipts = [
    receipt(1, '100.10', '2026-08-30', '2026-08-30T10:00:00Z'),
    receipt(2, '0.20', '2026-01-15', '2026-01-15T10:00:00Z'),
    receipt(3, '0.30', '2025-12-31', '2025-12-31T23:30:00Z'),
    receipt(4, '40.00', '2025-06-15', '2025-06-15T10:00:00Z'),
    receipt(5, '50.00', '2025-01-15', '2025-01-15T10:00:00Z'),
    receipt(6, '60.00', '2024-06-15', '2024-06-15T10:00:00Z'),
  ]
  serverReceiptFiles = Object.fromEntries(
    serverReceipts.map((item) => [item.file_id, receiptFile(item)]),
  )
  receiptUploadIndex = 0
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
    serverCouriers[0].documents[0].file.content_type = 'image/jpeg'
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:passport-preview')
    const page = await mountApp()

    await page.get('[data-od-id="courier-row-00000000-0000-4000-8000-000000000001"]').trigger('click')
    await flushPromises()
    await flushPromises()
    expect(page.get('[data-od-id="courier-detail-dialog"]').text()).toContain(
      'passport_scan.pdf',
    )
    expect(
      page.get('[data-od-id="document-card-document-1"] img').attributes('src'),
    ).toBe('blob:passport-preview')
    const previewRequest = requests.find(
      (request) => request.url === '/passport_scan.pdf?signature=test',
    )
    expect(previewRequest?.init.credentials).toBe('omit')

    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    await page.get('[data-copy-field="email"]').trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith('courier1@example.com')
    expect(page.get('[role="status"]').text()).toContain('Email скопировано')

    await page.get('[data-copy-field="phone"]').trigger('dblclick')
    await flushPromises()
    await flushPromises()
    expect(page.find('[data-od-id="edit-courier-dialog"]').exists()).toBe(true)
    await buttonWithText(page, 'Отмена').trigger('click')

    await page.get('[data-od-id="platform-status-platform-1"]').setValue('inactive')
    await buttonWithText(page, 'Изменить').trigger('click')
    await flushPromises()

    const platformRequest = requests.find((request) =>
      request.url.endsWith('/platform-accounts/platform-1'),
    )
    expect(platformRequest?.init.method).toBe('PATCH')
    expect(JSON.parse(String(platformRequest?.init.body))).toEqual({ status: 'inactive' })
    expect(page.get('.platform-row .status').text()).toBe('Неактивен')
    expect(page.get('[role="status"]').text()).toContain('Статус платформы изменён')

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

describe('Admin CRUD', () => {
  it('переключает вкладки и загружает cursor-страницы администраторов', async () => {
    const page = await mountApp()

    expect(page.get('[data-od-id="tab-couriers"]').attributes('aria-current')).toBe('page')
    await openAdminsTab(page)

    expect(page.get('[data-od-id="tab-admins"]').attributes('aria-current')).toBe('page')
    expect(page.get('[data-od-id="tab-couriers"]').attributes('aria-current')).toBeUndefined()
    expect(page.get('[data-od-id="admins-title"]').text()).toBe('Администраторы')
    expect(page.findAll('[data-od-id^="admin-row-"]')).toHaveLength(5)
    const listRequest = requests.find((request) => request.url.startsWith('/admin/admins?'))
    expect(new Headers(listRequest?.init.headers).get('Authorization')).toBe(
      'Bearer access-token',
    )

    await page.get('[aria-label="Следующая страница администраторов"]').trigger('click')
    await flushPromises()

    expect(page.findAll('[data-od-id^="admin-row-"]')).toHaveLength(1)
    expect(page.get('.pagination-summary').text()).toBe('Страница 2 · записей 1')
    expect(requests.some((request) => request.url.includes('cursor=admin-cursor-2'))).toBe(true)

    await page.get('[data-od-id="tab-couriers"]').trigger('click')
    await flushPromises()
    expect(page.get('[data-od-id="couriers-title"]').text()).toBe('Курьеры')
  })

  it('создаёт администратора с idempotency key и показывает конфликты', async () => {
    const page = await mountApp()
    await openAdminsTab(page)

    await page.get('[data-od-id="create-admin"]').trigger('click')
    await page.get('#admin-username').setValue('New.Operator')
    await page.get('#admin-telegramId').setValue('987654321')
    await page.get('#admin-password').setValue('new-password-123')
    await page.get('#admin-password-confirmation').setValue('new-password-123')
    await page.get('[data-od-id="create-admin-dialog"] form').trigger('submit')
    await flushPromises()
    await flushPromises()

    const createRequest = requests.find(
      (request) => request.url === '/admin/admins' && request.init.method === 'POST',
    )
    expect(new Headers(createRequest?.init.headers).get('Idempotency-Key')).toBeTruthy()
    expect(JSON.parse(String(createRequest?.init.body))).toEqual({
      username: 'new.operator',
      password: 'new-password-123',
      telegram_id: 987654321,
    })
    expect(page.text()).toContain('new.operator')
    expect(page.get('[role="status"]').text()).toContain('Администратор создан')

    await page.get('[data-od-id="create-admin"]').trigger('click')
    await page.get('#admin-username').setValue('root.admin')
    await page.get('#admin-password').setValue('duplicate-password')
    await page.get('#admin-password-confirmation').setValue('duplicate-password')
    await page.get('[data-od-id="create-admin-dialog"] form').trigger('submit')
    await flushPromises()

    expect(page.get('[data-od-id="create-admin-dialog"]').text()).toContain(
      'Администратор с таким username или Telegram ID уже существует.',
    )

    const conflictRequests = requests.filter(
      (request) => request.url === '/admin/admins' && request.init.method === 'POST',
    )
    const firstConflictKey = new Headers(conflictRequests.at(-1)?.init.headers).get(
      'Idempotency-Key',
    )
    await page.get('[data-od-id="create-admin-dialog"] form').trigger('submit')
    await flushPromises()
    const retriedRequests = requests.filter(
      (request) => request.url === '/admin/admins' && request.init.method === 'POST',
    )
    expect(new Headers(retriedRequests.at(-1)?.init.headers).get('Idempotency-Key')).toBe(
      firstConflictKey,
    )
  })

  it('читает, редактирует, меняет пароль и управляет статусом', async () => {
    const page = await mountApp()
    await openAdminsTab(page)
    const targetId = adminRecord(2).id

    await page.get(`[data-od-id="open-admin-${targetId}"]`).trigger('click')
    await flushPromises()
    expect(page.get('[data-od-id="admin-detail-dialog"]').text()).toContain('operator.2')
    expect(
      requests.some((request) => request.url === `/admin/admins/${targetId}`),
    ).toBe(true)

    await buttonWithText(page, 'Редактировать').trigger('click')
    await page.get('#edit-admin-username').setValue('Operator.Updated')
    await page.get('#edit-admin-telegramId').setValue('')
    await page.get('[data-od-id="edit-admin-dialog"] form').trigger('submit')
    await flushPromises()

    const patchRequest = requests.find(
      (request) => request.url === `/admin/admins/${targetId}` && request.init.method === 'PATCH',
    )
    expect(JSON.parse(String(patchRequest?.init.body))).toEqual({
      username: 'operator.updated',
      telegram_id: null,
    })
    expect(page.get('[data-od-id="admin-detail-dialog"]').text()).toContain('operator.updated')

    await buttonWithText(page, 'Сменить пароль').trigger('click')
    await page.get('#reset-admin-password').setValue('updated-password')
    await page.get('#reset-admin-password-confirmation').setValue('updated-password')
    await page.get('[data-od-id="reset-admin-password-dialog"] form').trigger('submit')
    await flushPromises()

    const passwordRequest = requests.find((request) =>
      request.url.endsWith(`/${targetId}/reset-password`),
    )
    expect(JSON.parse(String(passwordRequest?.init.body))).toEqual({
      new_password: 'updated-password',
    })

    await buttonWithText(page, 'Деактивировать').trigger('click')
    await page.get('[data-od-id="deactivate-admin-dialog"] .btn-danger').trigger('click')
    await flushPromises()

    expect(
      requests.some((request) => request.url === `/admin/admins/${targetId}/deactivate`),
    ).toBe(true)
    expect(page.get('[data-od-id="admin-detail-dialog"]').text()).toContain('Неактивен')

    await buttonWithText(page, 'Активировать').trigger('click')
    await flushPromises()
    expect(
      requests.some((request) => request.url === `/admin/admins/${targetId}/activate`),
    ).toBe(true)
    expect(page.get('[data-od-id="admin-detail-dialog"]').text()).toContain('Активен')
  })

  it('защищает текущую запись и синхронизирует сессию', async () => {
    const page = await mountApp()
    await openAdminsTab(page)

    await page.get(`[data-od-id="open-admin-${currentAdminId}"]`).trigger('click')
    await flushPromises()
    expect(buttonWithText(page, 'Текущая запись').attributes('disabled')).toBeDefined()

    await buttonWithText(page, 'Редактировать').trigger('click')
    await page.get('#edit-admin-username').setValue('root.renamed')
    await page.get('[data-od-id="edit-admin-dialog"] form').trigger('submit')
    await flushPromises()

    expect(page.get('[data-od-id="account-menu"] strong').text()).toBe('root.renamed')

    await buttonWithText(page, 'Сменить пароль').trigger('click')
    await page.get('#reset-admin-password').setValue('own-new-password')
    await page.get('#reset-admin-password-confirmation').setValue('own-new-password')
    await page.get('[data-od-id="reset-admin-password-dialog"] form').trigger('submit')
    await flushPromises()
    await flushPromises()

    expect(page.find('#loginTitle').exists()).toBe(true)
    expect(requests.some((request) => request.url === '/admin/auth/logout')).toBe(true)
  })
})

describe('Bikes full accounting', () => {
  it('фильтрует парк и управляет велосипедом и комплектацией', async () => {
    const page = await mountApp()
    await openBikesTab(page)

    expect(page.get('[data-od-id="bikes-title"]').text()).toBe('Велосипеды')
    expect(page.findAll('[data-od-id^="bike-row-"]')).toHaveLength(2)
    const listRequest = requests.find((request) => request.url.startsWith('/transport?'))
    expect(new Headers(listRequest?.init.headers).get('Authorization')).toBe('Bearer access-token')

    await page.get('[aria-label="Тип транспорта"]').setValue(' E-BIKE ')
    await page.get('[aria-label="Серийный номер"]').setValue(' bike-001 ')
    await page.get('[aria-label="Доступность"]').setValue('available')
    await page.get('.bikes-toolbar').trigger('submit')
    await flushPromises()
    expect(
      requests.some(
        (request) =>
          request.url.includes('type=e-bike') &&
          request.url.includes('serial_number=BIKE-001') &&
          request.url.includes('is_available=true'),
      ),
    ).toBe(true)
    await buttonWithText(page, 'Сбросить').trigger('click')
    await flushPromises()

    await page.get('[data-od-id="create-bike"]').trigger('click')
    await page.get('#bike-model').setValue('Urban Cargo')
    await page.get('#bike-serialNumber').setValue(' cargo-099 ')
    await page.get('#bike-color').setValue('Graphite')
    await page.get('#bike-rentalPrice').setValue('1500,50')
    await page.get('[data-od-id="bike-form-dialog"] form').trigger('submit')
    await flushPromises()
    await flushPromises()

    const createRequest = requests.find(
      (request) => request.url === '/transport' && request.init.method === 'POST',
    )
    expect(new Headers(createRequest?.init.headers).get('Idempotency-Key')).toBeTruthy()
    expect(JSON.parse(String(createRequest?.init.body))).toMatchObject({
      type: 'e-bike',
      model: 'Urban Cargo',
      serial_number: 'CARGO-099',
      color: 'Graphite',
      deposit_required: false,
      deposit_amount: null,
      rental_price: '1500.50',
    })
    expect(page.text()).toContain('Urban Cargo')

    const createdId = '20000000-0000-4000-8000-000000000099'
    await page.get(`[data-od-id="open-bike-${createdId}"]`).trigger('click')
    await flushPromises()
    await buttonWithText(page, 'Добавить позицию').trigger('click')
    await page.get('#component-name').setValue('Замок')
    await page.get('#component-unitPrice').setValue('25.50')
    await page.get('#component-quantity').setValue('2')
    await page.get('[data-od-id="component-form-dialog"] form').trigger('submit')
    await flushPromises()

    expect(page.get('[data-od-id="bike-detail-dialog"]').text()).toContain('51.00 Kč')
    const componentRequest = requests.find((request) => request.url.endsWith('/components'))
    expect(new Headers(componentRequest?.init.headers).get('Idempotency-Key')).toBeTruthy()

    await buttonWithText(page, 'Удалить').trigger('click')
    await page.get('[data-od-id="confirm-action-dialog"] .btn-danger').trigger('click')
    await flushPromises()
    expect(page.get('[data-od-id="bike-detail-dialog"]').text()).toContain('Комплектация не указана')

    await buttonWithText(page, 'Редактировать').trigger('click')
    await page.get('#bike-color').setValue('Silver')
    await page.get('[data-od-id="bike-form-dialog"] form').trigger('submit')
    await flushPromises()
    expect(page.get('[data-od-id="bike-detail-dialog"]').text()).toContain('Silver')
    const patchRequest = requests.find(
      (request) => request.url === `/transport/${createdId}` && request.init.method === 'PATCH',
    )
    expect(JSON.parse(String(patchRequest?.init.body))).toEqual({ color: 'Silver' })

    await buttonWithText(page, 'Удалить велосипед').trigger('click')
    await page.get('[data-od-id="confirm-action-dialog"] .btn-danger').trigger('click')
    await flushPromises()
    expect(page.find('[data-od-id="bike-detail-dialog"]').exists()).toBe(false)
  })

  it('выдаёт и возвращает велосипед, загружает и защищает договор', async () => {
    const page = await mountApp()
    await openBikesTab(page)
    const transportId = bike(1).id

    await page.get(`[data-od-id="open-bike-${transportId}"]`).trigger('click')
    await flushPromises()
    await buttonWithText(page, 'Выдать курьеру').trigger('click')
    await flushPromises()
    await page.get('[aria-label="Курьер"]').setValue(serverCouriers[0].id)
    await page.get('#rental-startedAt').setValue('2026-08-20T10:00')
    await page.get('[data-od-id="rental-form-dialog"] form').trigger('submit')
    await flushPromises()
    await flushPromises()

    const rentalRequest = requests.find((request) => request.url.endsWith('/rentals') && request.init.method === 'POST')
    expect(new Headers(rentalRequest?.init.headers).get('Idempotency-Key')).toBeTruthy()
    expect(page.get('[data-od-id="bike-detail-dialog"]').text()).toContain('Выдан')

    await buttonWithText(page, 'Приложить договор').trigger('click')
    const contract = new File(['signed'], 'contract.pdf', { type: 'application/pdf', lastModified: 1 })
    const fileInput = page.get('[data-od-id="contract-attach-dialog"] input[type="file"]')
    Object.defineProperty(fileInput.element, 'files', { value: [contract], configurable: true })
    await fileInput.trigger('change')
    await buttonWithText(page, 'Загрузить и приложить').trigger('click')
    await flushPromises()
    await flushPromises()

    const uploadRequest = requests.find((request) => request.url === '/upload/contract')
    expect(uploadRequest?.init.method).toBe('PUT')
    expect(uploadRequest?.init.credentials).toBe('omit')
    expect(new Headers(uploadRequest?.init.headers).get('Authorization')).toBeNull()
    expect(requests.some((request) => request.url.endsWith('/contract-file/confirm'))).toBe(true)
    expect(requests.some((request) => request.url.endsWith('/rental-transport-1/contract'))).toBe(true)
    expect(page.get('[data-od-id="bike-detail-dialog"]').text()).toContain('contract.pdf')

    let downloaded = ''
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      downloaded = this.href
    })
    await buttonWithText(page, 'Скачать договор').trigger('click')
    await flushPromises()
    expect(downloaded).toBe('https://storage.test/download/contract.pdf')

    await buttonWithText(page, 'Завершить аренду').trigger('click')
    await page.get('#rental-endedAt').setValue('2026-08-21T10:00')
    await page.get('[data-od-id="rental-form-dialog"] form').trigger('submit')
    await flushPromises()
    await flushPromises()
    expect(page.get('[data-od-id="bike-detail-dialog"]').text()).toContain('Велосипед свободен')

    await buttonWithText(page, 'Удалить велосипед').trigger('click')
    await page.get('[data-od-id="confirm-action-dialog"] .btn-danger').trigger('click')
    await flushPromises()
    expect(page.get('[data-od-id="confirm-action-dialog"]').text()).toContain(
      'Велосипед нельзя удалить: в истории есть подписанный договор.',
    )
  })
})

describe('Finance receipts', () => {
  it('загружает все cursor-страницы и показывает статистику по годам', async () => {
    window.localStorage.setItem(
      'mfs.finance.pending-file-cleanup',
      JSON.stringify(['already-deleted-file']),
    )
    const page = await mountApp()
    await openFinanceTab(page)

    expect(page.get('[data-od-id="tab-finance"]').attributes('aria-current')).toBe('page')
    expect(page.get('[data-od-id="finance-title"]').text()).toBe('Чеки и расходы')
    expect(page.findAll('[data-od-id^="receipt-row-"]')).toHaveLength(5)
    expect(page.get('[data-od-id="receipt-stats-amount"]').text()).toBe('100.30 Kč')
    expect(page.get('[data-od-id="receipt-stats-count"]').text()).toBe('2')
    expect(
      requests.some(
        (request) =>
          request.url === '/files/already-deleted-file' && request.init.method === 'DELETE',
      ),
    ).toBe(true)
    expect(window.localStorage.getItem('mfs.finance.pending-file-cleanup')).toBeNull()
    expect(
      requests.some(
        (request) =>
          request.url.includes('/receipts?limit=200') &&
          request.url.includes('cursor=receipt-cursor-3'),
      ),
    ).toBe(true)

    await page.get('[data-od-id="receipt-stats-year"]').setValue('2025')
    expect(page.get('[data-od-id="receipt-stats-amount"]').text()).toBe('90.30 Kč')
    expect(page.get('[data-od-id="receipt-stats-count"]').text()).toBe('3')

    await page.get('[aria-label="Следующая страница чеков"]').trigger('click')
    await flushPromises()
    expect(page.findAll('[data-od-id^="receipt-row-"]')).toHaveLength(1)
    expect(page.get('.pagination-summary').text()).toBe('Страница 2 · записей 1')
  })

  it('создаёт, читает, заменяет файл и удаляет чек', async () => {
    const page = await mountApp()
    await openFinanceTab(page)

    await page.get('[data-od-id="create-receipt"]').trigger('click')
    await page.get('#receipt-amount').setValue('125,50')
    await page.get('#receipt-date').setValue('2026-08-29')
    const newReceiptFile = new File(['receipt'], 'receipt-new.pdf', {
      type: 'application/pdf',
      lastModified: 1,
    })
    const createFileInput = page.get('#receipt-file')
    Object.defineProperty(createFileInput.element, 'files', {
      value: [newReceiptFile],
      configurable: true,
    })
    await createFileInput.trigger('change')
    await page.get('[data-od-id="receipt-form-dialog"] form').trigger('submit')
    await flushPromises()
    await flushPromises()

    const createRequest = requests.find(
      (request) => request.url === '/receipts' && request.init.method === 'POST',
    )
    expect(new Headers(createRequest?.init.headers).get('Idempotency-Key')).toBeTruthy()
    expect(JSON.parse(String(createRequest?.init.body))).toEqual({
      file_id: 'receipt-upload-file-1',
      amount: '125.50',
      date: '2026-08-29',
    })
    expect(requests.some((request) => request.url === '/upload/receipt-upload-file-1')).toBe(true)
    expect(requests.some((request) => request.url.endsWith('/receipt-upload-file-1/confirm'))).toBe(true)
    expect(page.get('[role="status"]').text()).toContain('Чек добавлен')

    const createdId = '30000000-0000-4000-8000-000000000099'
    await page.get(`[data-od-id="open-receipt-${createdId}"]`).trigger('click')
    await flushPromises()
    expect(page.get('[data-od-id="receipt-detail-dialog"]').text()).toContain('receipt-new.pdf')
    expect(page.get('[data-od-id="receipt-detail-dialog"]').text()).toContain('29.08.2026')

    let downloadedHref = ''
    let downloadedName = ''
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      downloadedHref = this.href
      downloadedName = this.download
    })
    const fileReadsBeforeDownload = requests.filter(
      (request) => request.url === '/files/receipt-upload-file-1',
    ).length
    await buttonWithText(page, 'Скачать').trigger('click')
    await flushPromises()
    expect(
      requests.filter((request) => request.url === '/files/receipt-upload-file-1'),
    ).toHaveLength(fileReadsBeforeDownload + 1)
    expect(downloadedHref).toBe('https://storage.test/download/receipt-upload-file-1')
    expect(downloadedName).toBe('receipt-new.pdf')

    await buttonWithText(page, 'Редактировать').trigger('click')
    await page.get('#receipt-amount').setValue('130.75')
    await page.get('#receipt-date').setValue('2025-12-31')
    const replacement = new File(['replacement'], 'replacement.png', {
      type: 'image/png',
      lastModified: 2,
    })
    const editFileInput = page.get('#receipt-file')
    Object.defineProperty(editFileInput.element, 'files', {
      value: [replacement],
      configurable: true,
    })
    await editFileInput.trigger('change')
    await page.get('[data-od-id="receipt-form-dialog"] form').trigger('submit')
    await flushPromises()
    await flushPromises()

    const patchRequest = requests.find(
      (request) => request.url === `/receipts/${createdId}` && request.init.method === 'PATCH',
    )
    expect(JSON.parse(String(patchRequest?.init.body))).toEqual({
      file_id: 'receipt-upload-file-2',
      amount: '130.75',
      date: '2025-12-31',
    })
    expect(
      requests.some(
        (request) =>
          request.url === '/files/receipt-upload-file-1' && request.init.method === 'DELETE',
      ),
    ).toBe(true)
    expect(page.get('[data-od-id="receipt-detail-dialog"]').text()).toContain('replacement.png')
    expect(page.get('[data-od-id="receipt-detail-dialog"]').text()).toContain('31.12.2025')

    await buttonWithText(page, 'Удалить').trigger('click')
    await page.get('[data-od-id="delete-receipt-dialog"] .btn-danger').trigger('click')
    await flushPromises()
    await flushPromises()

    const receiptDeleteIndex = requests.findIndex(
      (request) => request.url === `/receipts/${createdId}` && request.init.method === 'DELETE',
    )
    const fileDeleteIndex = requests.findIndex(
      (request) =>
        request.url === '/files/receipt-upload-file-2' && request.init.method === 'DELETE',
    )
    expect(receiptDeleteIndex).toBeGreaterThan(-1)
    expect(fileDeleteIndex).toBeGreaterThan(receiptDeleteIndex)
    expect(page.find('[data-od-id="receipt-detail-dialog"]').exists()).toBe(false)
    expect(page.get('[role="status"]').text()).toContain('Чек удалён')
  })
})
