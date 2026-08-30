import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { DocumentTemplate } from '../../types/document'
import DocumentsAdmin from './DocumentsAdmin.vue'

const documentApi = vi.hoisted(() => ({
  list: vi.fn(),
  get: vi.fn(),
  create: vi.fn(),
  render: vi.fn(),
  remove: vi.fn(),
}))

const filesApi = vi.hoisted(() => ({
  requestUpload: vi.fn(),
  put: vi.fn(),
  confirm: vi.fn(),
  remove: vi.fn(),
}))

vi.mock('../../api/documents', () => ({
  listDocumentTemplates: documentApi.list,
  getDocumentTemplate: documentApi.get,
  createDocumentTemplate: documentApi.create,
  renderDocumentTemplate: documentApi.render,
  deleteDocumentTemplate: documentApi.remove,
  documentErrorMessage: (_error: unknown, fallback: string) => fallback,
}))

vi.mock('../../api/files', () => ({
  requestFileUpload: filesApi.requestUpload,
  putFile: filesApi.put,
  confirmFileUpload: filesApi.confirm,
  deleteFile: filesApi.remove,
}))

const docxContentType =
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
let wrapper: VueWrapper | undefined

function template(id = '40000000-0000-4000-8000-000000000001'): DocumentTemplate {
  return {
    id,
    name: 'Договор аренды',
    fileId: '50000000-0000-4000-8000-000000000001',
    fields: {
      courier: ['full_name', 'city'],
      rental: ['started_at'],
    },
    createdAt: '2026-08-30T10:00:00Z',
    updatedAt: '2026-08-30T10:00:00Z',
  }
}

async function mountDocuments() {
  wrapper = mount(DocumentsAdmin, {
    global: { stubs: { Teleport: true } },
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
  const localValues = new Map<string, string>()
  Object.defineProperty(window, 'localStorage', {
    configurable: true,
    value: {
      getItem: (key: string) => localValues.get(key) ?? null,
      setItem: (key: string, value: string) => localValues.set(key, value),
      removeItem: (key: string) => localValues.delete(key),
      clear: () => localValues.clear(),
    },
  })
  const record = template()
  documentApi.list.mockReset().mockResolvedValue({ items: [record], nextCursor: null })
  documentApi.get.mockReset().mockResolvedValue(record)
  documentApi.create.mockReset().mockResolvedValue(record)
  documentApi.render.mockReset().mockResolvedValue(new Blob(['generated-docx']))
  documentApi.remove.mockReset().mockResolvedValue(undefined)
  filesApi.requestUpload.mockReset().mockResolvedValue({
    file_id: record.fileId,
    upload_url: 'https://storage.test/upload/template',
    content_type: docxContentType,
    expires_in: 900,
  })
  filesApi.put.mockReset().mockResolvedValue('template-etag')
  filesApi.confirm.mockReset().mockResolvedValue(undefined)
  filesApi.remove.mockReset().mockResolvedValue(undefined)
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:generated-document')
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
})

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})

describe('DocumentsAdmin', () => {
  it('использует cursor-пагинацию', async () => {
    const first = template()
    const second = template('40000000-0000-4000-8000-000000000002')
    documentApi.list
      .mockReset()
      .mockResolvedValueOnce({ items: [first], nextCursor: 'cursor-2' })
      .mockResolvedValueOnce({ items: [second], nextCursor: null })
    const page = await mountDocuments()

    await page.get('[aria-label="Следующая страница шаблонов"]').trigger('click')
    await flushPromises()

    expect(documentApi.list).toHaveBeenNthCalledWith(1, { cursor: null, limit: 5 })
    expect(documentApi.list).toHaveBeenNthCalledWith(2, { cursor: 'cursor-2', limit: 5 })
    expect(page.get('.pagination-summary').text()).toBe('Страница 2 · шаблонов 1')
  })

  it('загружает DOCX и создаёт шаблон', async () => {
    const page = await mountDocuments()
    await page.get('[data-od-id="create-document-template"]').trigger('click')
    expect(page.get('[data-od-id="document-template-form-dialog"]').text()).toContain(
      '{courier.full_name}',
    )
    expect(page.get('[data-od-id="document-template-form-dialog"]').text()).toContain(
      'строчные латинские буквы',
    )
    await page.get('#document-template-name').setValue('  Договор аренды  ')
    const invalidFile = new File(['not-docx'], 'template.pdf', {
      type: 'application/pdf',
      lastModified: 1,
    })
    const fileInput = page.get('#document-template-file')
    Object.defineProperty(fileInput.element, 'files', {
      value: [invalidFile],
      configurable: true,
    })
    await fileInput.trigger('change')
    expect(page.get('#document-template-file-error').text()).toContain('DOCX')
    expect(filesApi.requestUpload).not.toHaveBeenCalled()

    const docx = new File(['template'], 'rental.docx', {
      type: docxContentType,
      lastModified: 2,
    })
    Object.defineProperty(fileInput.element, 'files', {
      value: [docx],
      configurable: true,
    })
    await fileInput.trigger('change')
    await page.get('[data-od-id="document-template-form-dialog"] form').trigger('submit')
    await flushPromises()
    await flushPromises()

    expect(filesApi.requestUpload).toHaveBeenCalledWith(docx)
    expect(filesApi.put).toHaveBeenCalledWith(
      'https://storage.test/upload/template',
      docxContentType,
      docx,
    )
    expect(filesApi.confirm).toHaveBeenCalledWith(
      '50000000-0000-4000-8000-000000000001',
      'template-etag',
    )
    expect(documentApi.create).toHaveBeenCalledWith({
      name: 'Договор аренды',
      fileId: '50000000-0000-4000-8000-000000000001',
    })
    expect(filesApi.remove).not.toHaveBeenCalled()
    expect(page.get('[role="status"]').text()).toContain('Шаблон добавлен')
  })

  it('очищает загруженный файл после отменённого создания', async () => {
    documentApi.create.mockRejectedValueOnce(new Error('Шаблон не создан'))
    const page = await mountDocuments()
    await page.get('[data-od-id="create-document-template"]').trigger('click')
    await page.get('#document-template-name').setValue('Черновик')
    const docx = new File(['template'], 'draft.docx', {
      type: docxContentType,
      lastModified: 3,
    })
    const fileInput = page.get('#document-template-file')
    Object.defineProperty(fileInput.element, 'files', {
      value: [docx],
      configurable: true,
    })
    await fileInput.trigger('change')
    await page.get('[data-od-id="document-template-form-dialog"] form').trigger('submit')
    await flushPromises()

    expect(page.get('.form-api-error').text()).toContain('Шаблон не создан')
    await page
      .get('[data-od-id="document-template-form-dialog"] [aria-label="Закрыть"]')
      .trigger('click')
    await flushPromises()

    expect(filesApi.remove).toHaveBeenCalledWith(
      '50000000-0000-4000-8000-000000000001',
    )
  })

  it('показывает схему, формирует DOCX и удаляет только шаблон', async () => {
    const page = await mountDocuments()
    const record = template()
    await page.get(`[data-od-id="open-document-template-${record.id}"]`).trigger('click')
    await flushPromises()

    expect(documentApi.get).toHaveBeenCalledWith(record.id)
    expect(page.get('[data-od-id="document-template-detail-dialog"]').text()).toContain(
      '{courier.full_name}',
    )

    let downloadedHref = ''
    let downloadedName = ''
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      downloadedHref = this.href
      downloadedName = this.download
    })
    await page.get('[data-od-id="render-document"]').trigger('click')
    await page.get('#document-value-courier-full_name').setValue('Иван Новак')
    await page.get('#document-value-courier-city').setValue('Прага')
    await page.get('#document-value-rental-started_at').setValue('30.08.2026')
    await page.get('[data-od-id="document-render-dialog"] form').trigger('submit')
    await flushPromises()

    expect(documentApi.render).toHaveBeenCalledWith(record.id, {
      courier: { full_name: 'Иван Новак', city: 'Прага' },
      rental: { started_at: '30.08.2026' },
    })
    expect(downloadedHref).toBe('blob:generated-document')
    expect(downloadedName).toBe('Договор аренды.docx')
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:generated-document')

    await buttonWithText(page, 'Назад').trigger('click')
    await buttonWithText(page, 'Удалить').trigger('click')
    await page.get('[data-od-id="delete-document-template-dialog"] .btn-danger').trigger('click')
    await flushPromises()
    await flushPromises()

    expect(documentApi.remove).toHaveBeenCalledWith(record.id)
    expect(filesApi.remove).not.toHaveBeenCalled()
    expect(page.find('[data-od-id="document-template-detail-dialog"]').exists()).toBe(false)
    expect(page.get('[role="status"]').text()).toContain('Шаблон удалён')
  })
})
