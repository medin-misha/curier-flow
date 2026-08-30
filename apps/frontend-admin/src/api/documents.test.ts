import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, configureAccessRecovery, setAccessToken } from './client'
import {
  createDocumentTemplate,
  deleteDocumentTemplate,
  documentErrorMessage,
  getDocumentTemplate,
  listDocumentTemplates,
  renderDocumentTemplate,
} from './documents'

const responseBody = {
  id: '40000000-0000-4000-8000-000000000001',
  name: 'Договор аренды',
  file_id: '50000000-0000-4000-8000-000000000001',
  fields: { courier: ['full_name'], rental: ['started_at'] },
  created_at: '2026-08-30T10:00:00Z',
  updated_at: '2026-08-30T10:00:00Z',
}

afterEach(() => {
  setAccessToken(null)
  configureAccessRecovery(null)
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('Documents API', () => {
  it('маппит реестр и выполняет полный контракт, включая бинарный render', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ items: [responseBody], next_cursor: 'cursor-2' }), {
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(responseBody), {
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(responseBody), {
          status: 201,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(
        new Response('generated-docx', {
          headers: {
            'Content-Type':
              'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
          },
        }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)
    setAccessToken('documents-token')

    const page = await listDocumentTemplates({ cursor: null, limit: 5 })
    const detail = await getDocumentTemplate(responseBody.id)
    const created = await createDocumentTemplate({
      name: responseBody.name,
      fileId: responseBody.file_id,
    })
    const rendered = await renderDocumentTemplate(responseBody.id, {
      courier: { full_name: 'Иван Новак' },
      rental: { started_at: '30.08.2026' },
    })
    await deleteDocumentTemplate(responseBody.id)

    expect(page).toEqual({
      items: [
        {
          id: responseBody.id,
          name: responseBody.name,
          fileId: responseBody.file_id,
          fields: responseBody.fields,
          createdAt: responseBody.created_at,
          updatedAt: responseBody.updated_at,
        },
      ],
      nextCursor: 'cursor-2',
    })
    expect(detail.fileId).toBe(responseBody.file_id)
    expect(created.name).toBe(responseBody.name)
    expect(await rendered.text()).toBe('generated-docx')

    expect(fetchMock.mock.calls.map(([path]) => path)).toEqual([
      '/document-templates?limit=5',
      `/document-templates/${responseBody.id}`,
      '/document-templates',
      `/document-templates/${responseBody.id}/render`,
      `/document-templates/${responseBody.id}`,
    ])
    expect(JSON.parse(String(fetchMock.mock.calls[2]?.[1]?.body))).toEqual({
      name: responseBody.name,
      file_id: responseBody.file_id,
    })
    expect(JSON.parse(String(fetchMock.mock.calls[3]?.[1]?.body))).toEqual({
      values: {
        courier: { full_name: 'Иван Новак' },
        rental: { started_at: '30.08.2026' },
      },
    })
    for (const [, options] of fetchMock.mock.calls) {
      expect(new Headers(options?.headers).get('Authorization')).toBe('Bearer documents-token')
      expect(options).not.toHaveProperty('responseType')
    }
  })

  it('объясняет ошибки синтаксиса полей DOCX', () => {
    expect(
      documentErrorMessage(
        new ApiError(422, {
          reason: 'invalid-docx-template',
          detail: 'Malformed placeholder: {группа.поле}',
        }),
        'Не удалось создать шаблон.',
      ),
    ).toBe(
      'Некорректное поле {группа.поле}. Используйте формат {courier.full_name}: только строчные латинские буквы, цифры и _.',
    )
    expect(
      documentErrorMessage(
        new ApiError(422, {
          reason: 'invalid-docx-template',
          detail: 'DOCX template contains no placeholders',
        }),
        'Не удалось создать шаблон.',
      ),
    ).toBe('Поля не найдены. Добавьте хотя бы одно поле в формате {courier.full_name}.')
  })
})
