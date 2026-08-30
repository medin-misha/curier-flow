import { ref } from 'vue'
import {
  createDocumentTemplate,
  deleteDocumentTemplate,
  documentErrorMessage,
  getDocumentTemplate,
  listDocumentTemplates,
} from '../api/documents'
import { ApiError } from '../api/client'
import type { DocumentTemplate, DocumentTemplateCreateInput } from '../types/document'

const PAGE_SIZE = 5

export function useDocumentTemplatesRegistry() {
  const templates = ref<DocumentTemplate[]>([])
  const currentPage = ref(1)
  const cursors = ref<Array<string | null>>([null])
  const nextCursor = ref<string | null>(null)
  const loading = ref(false)
  const loadError = ref('')
  let loadSequence = 0

  async function loadPage(page: number) {
    const cursor = cursors.value[page - 1]
    if (cursor === undefined) return
    const sequence = ++loadSequence
    currentPage.value = page
    loading.value = true
    loadError.value = ''
    try {
      const result = await listDocumentTemplates({ cursor, limit: PAGE_SIZE })
      if (sequence !== loadSequence) return
      templates.value = result.items
      nextCursor.value = result.nextCursor
    } catch (error) {
      if (sequence !== loadSequence) return
      loadError.value = documentErrorMessage(error, 'Не удалось получить список шаблонов.')
    } finally {
      if (sequence === loadSequence) loading.value = false
    }
  }

  async function pageTo(page: number) {
    if (page < 1) return
    if (page === currentPage.value + 1) {
      if (!nextCursor.value) return
      cursors.value[page - 1] = nextCursor.value
    }
    await loadPage(page)
  }

  async function reloadFirstPage() {
    cursors.value = [null]
    nextCursor.value = null
    currentPage.value = 1
    await loadPage(1)
  }

  function replaceTemplate(updated: DocumentTemplate) {
    const index = templates.value.findIndex((template) => template.id === updated.id)
    if (index >= 0) templates.value[index] = updated
    return updated
  }

  async function create(input: DocumentTemplateCreateInput) {
    const created = await createDocumentTemplate(input)
    await reloadFirstPage()
    return created
  }

  async function remove(templateId: string) {
    try {
      await deleteDocumentTemplate(templateId)
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 404) throw error
    }
    await reloadFirstPage()
  }

  return {
    templates,
    currentPage,
    nextCursor,
    loading,
    loadError,
    loadPage,
    pageTo,
    reloadFirstPage,
    replaceTemplate,
    retrieve: getDocumentTemplate,
    create,
    remove,
  }
}
