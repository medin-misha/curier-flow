import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Courier } from '../../types/courier'
import type { DocumentRenderValues, DocumentTemplate } from '../../types/document'
import type { Transport, TransportRental } from '../../types/transport'
import DocumentRenderModal from './DocumentRenderModal.vue'

const courierApi = vi.hoisted(() => ({
  list: vi.fn(),
  get: vi.fn(),
}))

const transportApi = vi.hoisted(() => ({
  list: vi.fn(),
  get: vi.fn(),
  listRentals: vi.fn(),
}))

vi.mock('../../api/couriers', () => ({
  listCouriers: courierApi.list,
  getCourier: courierApi.get,
}))

vi.mock('../../api/transports', () => ({
  listTransports: transportApi.list,
  getTransport: transportApi.get,
  listTransportRentals: transportApi.listRentals,
}))

const courier: Courier = {
  id: 'courier-1',
  fullName: 'Иван Новак',
  email: 'ivan@example.test',
  phone: '+420111222333',
  birthDate: '1990-04-12',
  city: 'Прага',
  address: 'Главная 1',
  citizenship: 'CZ',
  bank: 'CZ001234',
  contactPlatform: null,
  contact: null,
  source: null,
  consent: true,
  consentAt: '2026-08-20T10:00:00Z',
  platforms: [],
  documents: 0,
  documentFiles: [],
  documentStatus: 'Нет документов',
  createdAt: '2026-08-20T10:00:00Z',
  updatedAt: '2026-08-21T10:00:00Z',
  updated: '21.08.2026',
}

const rental: TransportRental = {
  id: 'rental-1',
  transportId: 'transport-1',
  courierId: courier.id,
  paymentType: 'weekly_in_arrears',
  startedAt: '2026-08-30T10:00:00Z',
  endedAt: null,
  fileId: null,
  file: null,
  isActive: true,
  createdAt: '2026-08-30T10:00:00Z',
  updatedAt: '2026-08-30T10:00:00Z',
}

const transport: Transport = {
  id: 'transport-1',
  type: 'bike',
  model: 'Urban Arrow',
  serialNumber: 'SN-001',
  ordinalNumber: 42,
  color: 'black',
  depositRequired: true,
  depositAmount: '2000.00',
  rentalPrice: '1500.00',
  isAvailable: false,
  lastRental: {
    id: rental.id,
    courier: { id: rental.courierId, fullName: null, phone: null },
    startedAt: rental.startedAt,
    endedAt: rental.endedAt,
    isActive: rental.isActive,
  },
  components: [],
  activeRental: rental,
  comment: null,
  debtAmount: '0.00',
  createdAt: '2026-08-20T10:00:00Z',
  updatedAt: '2026-08-21T10:00:00Z',
}

const template: DocumentTemplate = {
  id: 'template-1',
  name: 'Договор аренды',
  fileId: 'file-1',
  fields: {
    courier: ['full_name', 'city', 'date_of_birth'],
    transport: ['model', 'serial_number', 'ordinal_number', 'deposit_required'],
    transport_courier: ['started_at', 'is_active', 'payment_type'],
    manual: ['contract_number'],
  },
  createdAt: '2026-08-30T10:00:00Z',
  updatedAt: '2026-08-30T10:00:00Z',
}

beforeEach(() => {
  courierApi.list.mockReset().mockResolvedValue({ items: [courier], nextCursor: null })
  courierApi.get.mockReset().mockResolvedValue(courier)
  transportApi.list.mockReset().mockResolvedValue({ items: [transport], nextCursor: null })
  transportApi.get.mockReset().mockResolvedValue(transport)
  transportApi.listRentals.mockReset().mockResolvedValue({ items: [rental], nextCursor: null })
})

describe('DocumentRenderModal', () => {
  it('заполняет поля моделей и сохраняет ручные изменения', async () => {
    const wrapper = mount(DocumentRenderModal, {
      props: { template, rendering: false, error: '' },
      global: { stubs: { Teleport: true } },
    })
    await flushPromises()

    await wrapper.get('#document-courier').setValue(courier.id)
    await flushPromises()
    expect(wrapper.get('#document-transport').attributes('disabled')).toBeUndefined()
    await wrapper.get('#document-transport').setValue(transport.id)
    expect(wrapper.get('#document-transport').element).toHaveProperty('value', transport.id)
    await flushPromises()
    await wrapper.get('#document-rental').setValue(rental.id)
    await flushPromises()

    expect(wrapper.get('#document-value-courier-full_name').element).toHaveProperty(
      'value',
      'Иван Новак',
    )
    expect(wrapper.get('#document-value-courier-date_of_birth').element).toHaveProperty(
      'value',
      '12.04.1990',
    )
    expect(wrapper.get('#document-value-transport-deposit_required').element).toHaveProperty(
      'value',
      'Да',
    )
    expect(wrapper.get('#document-value-transport_courier-started_at').element).toHaveProperty(
      'value',
      '30.08.2026',
    )

    await wrapper.get('#document-value-courier-city').setValue('Брно')
    await wrapper.get('#document-courier').setValue('')
    await wrapper.get('#document-courier').setValue(courier.id)
    await flushPromises()
    expect(wrapper.get('#document-value-courier-city').element).toHaveProperty('value', 'Брно')

    await wrapper.get('#document-value-manual-contract_number').setValue('A-42')
    await wrapper.get('form').trigger('submit')

    const rendered = wrapper.emitted('render')?.[0]?.[0] as DocumentRenderValues
    expect(rendered.courier).toMatchObject({
      full_name: 'Иван Новак',
      city: 'Брно',
      date_of_birth: '12.04.1990',
    })
    expect(rendered.transport).toMatchObject({
      model: 'Urban Arrow',
      serial_number: 'SN-001',
      ordinal_number: '42',
      deposit_required: 'Да',
    })
    expect(rendered.transport_courier).toEqual({ started_at: '30.08.2026', is_active: 'Да', payment_type: 'Неделя назад' })
    expect(rendered.manual).toEqual({ contract_number: 'A-42' })
  })

  it('оставляет пустыми необязательный номер и незаполненный тип оплаты прежней аренды', async () => {
    transportApi.get.mockResolvedValueOnce({ ...transport, ordinalNumber: null })
    transportApi.listRentals.mockResolvedValueOnce({ items: [{ ...rental, paymentType: null }], nextCursor: null })
    const wrapper = mount(DocumentRenderModal, {
      props: { template, rendering: false, error: '' },
      global: { stubs: { Teleport: true } },
    })
    await flushPromises()
    await wrapper.get('#document-transport').setValue(transport.id)
    await flushPromises()
    await wrapper.get('#document-rental').setValue(rental.id)
    await flushPromises()
    expect(wrapper.get('#document-value-transport-ordinal_number').element).toHaveProperty('value', '')
    expect(wrapper.get('#document-value-transport_courier-payment_type').element).toHaveProperty('value', '')
  })

  it('блокирует рендер для аренды другого курьера', async () => {
    const otherCourier = { ...courier, id: 'courier-2', fullName: 'Петр Новак' }
    courierApi.list.mockResolvedValueOnce({ items: [courier, otherCourier], nextCursor: null })
    courierApi.get.mockResolvedValueOnce(otherCourier)
    const wrapper = mount(DocumentRenderModal, {
      props: { template, rendering: false, error: '' },
      global: { stubs: { Teleport: true } },
    })
    await flushPromises()

    await wrapper.get('#document-courier').setValue(otherCourier.id)
    await flushPromises()
    expect(wrapper.get('#document-transport').attributes('disabled')).toBeUndefined()
    await wrapper.get('#document-transport').setValue(transport.id)
    await flushPromises()
    await wrapper.get('#document-rental').setValue(rental.id)
    await flushPromises()

    expect(wrapper.text()).toContain('Выбранная аренда относится к другому курьеру.')
    expect(wrapper.get('[data-od-id="download-rendered-document"]').attributes('disabled')).toBeDefined()
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('render')).toBeUndefined()
  })
})
