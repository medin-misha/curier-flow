<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ApiError } from '../../api/client'
import { documentErrorMessage, renderDocumentTemplate } from '../../api/documents'
import {
  confirmFileUpload,
  deleteFile,
  putFile,
  requestFileUpload,
} from '../../api/files'
import { useDocumentTemplatesRegistry } from '../../composables/useDocumentTemplatesRegistry'
import type {
  DocumentRenderValues,
  DocumentTemplate,
  DocumentTemplateFormInput,
} from '../../types/document'
import AppToast from '../ui/AppToast.vue'
import DocumentRenderModal from './DocumentRenderModal.vue'
import DocumentTemplateDeleteModal from './DocumentTemplateDeleteModal.vue'
import DocumentTemplateDetailsModal from './DocumentTemplateDetailsModal.vue'
import DocumentTemplateFormModal from './DocumentTemplateFormModal.vue'
import DocumentsRegistry from './DocumentsRegistry.vue'

interface UploadAttempt {
  signature: string
  fileId: string | null
  ready: boolean
}

const emit = defineEmits<{
  busyChange: [busy: boolean]
}>()

const cleanupStorageKey = 'mfs.documents.pending-file-cleanup'
const registry = useDocumentTemplatesRegistry()
const selectedTemplate = ref<DocumentTemplate | null>(null)
const createOpen = ref(false)
const renderOpen = ref(false)
const deleteOpen = ref(false)
const saving = ref(false)
const rendering = ref(false)
const deleting = ref(false)
const detailsRefreshing = ref(false)
const formError = ref('')
const renderError = ref('')
const deleteError = ref('')
const toastVisible = ref(false)
const toastTitle = ref('')
const toastMessage = ref('')
const lastFocused = ref<HTMLElement | null>(null)
const fileIdentities = new WeakMap<File, string>()
let uploadAttempt: UploadAttempt | null = null
let detailsSequence = 0
let toastTimer: ReturnType<typeof setTimeout> | undefined
let disposed = false

const paginationSummary = computed(
  () => `Страница ${registry.currentPage.value} · шаблонов ${registry.templates.value.length}`,
)

watch([createOpen, renderOpen, deleteOpen, selectedTemplate], () => {
  document.body.classList.toggle(
    'modal-open',
    createOpen.value || renderOpen.value || deleteOpen.value || Boolean(selectedTemplate.value),
  )
})

watch(
  [saving, rendering, deleting],
  () => emit('busyChange', saving.value || rendering.value || deleting.value),
  { immediate: true },
)

function rememberFocus(trigger?: EventTarget | null) {
  lastFocused.value =
    trigger instanceof HTMLElement ? trigger : (document.activeElement as HTMLElement | null)
}

function restoreFocus() {
  void nextTick(() => lastFocused.value?.focus())
}

function showToast(title: string, message: string) {
  toastTitle.value = title
  toastMessage.value = message
  toastVisible.value = true
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => {
    toastVisible.value = false
  }, 4_200)
}

function actionErrorMessage(error: unknown, fallback: string) {
  if (error instanceof Error && !(error as Error & { status?: number }).status) return error.message
  return documentErrorMessage(error, fallback)
}

function pendingCleanupIds() {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(cleanupStorageKey) ?? '[]') as unknown
    return Array.isArray(parsed)
      ? parsed.filter((value): value is string => typeof value === 'string')
      : []
  } catch {
    return []
  }
}

function updatePendingCleanup(fileId: string, pending: boolean) {
  try {
    const ids = new Set(pendingCleanupIds())
    if (pending) ids.add(fileId)
    else ids.delete(fileId)
    if (ids.size) window.localStorage.setItem(cleanupStorageKey, JSON.stringify([...ids]))
    else window.localStorage.removeItem(cleanupStorageKey)
  } catch {
    // Очистка выполняется сразу; localStorage нужен только для повторной попытки.
  }
}

async function cleanupFile(fileId: string) {
  updatePendingCleanup(fileId, true)
  try {
    await deleteFile(fileId)
    updatePendingCleanup(fileId, false)
    return true
  } catch (error) {
    if (
      error instanceof ApiError &&
      (error.status === 404 || error.problem?.reason === 'file-in-use')
    ) {
      updatePendingCleanup(fileId, false)
      return true
    }
    return false
  }
}

async function retryPendingFileCleanup() {
  await Promise.all(pendingCleanupIds().map(cleanupFile))
}

async function cleanupUploadAttempt() {
  const fileId = uploadAttempt?.fileId
  uploadAttempt = null
  if (fileId) await cleanupFile(fileId)
}

async function uploadTemplateFile(file: File) {
  let signature = fileIdentities.get(file)
  if (!signature) {
    signature = crypto.randomUUID()
    fileIdentities.set(file, signature)
  }
  if (!uploadAttempt || uploadAttempt.signature !== signature) {
    await cleanupUploadAttempt()
    uploadAttempt = { signature, fileId: null, ready: false }
  }
  const attempt = uploadAttempt
  if (!attempt) throw new Error('Загрузка файла была отменена.')

  async function requireActiveAttempt() {
    if (!disposed && uploadAttempt === attempt) return
    if (attempt.fileId) await cleanupFile(attempt.fileId)
    throw new Error('Загрузка файла была отменена.')
  }

  if (!attempt.ready) {
    if (attempt.fileId) {
      await cleanupFile(attempt.fileId)
      attempt.fileId = null
    }
    const ticket = await requestFileUpload(file)
    attempt.fileId = ticket.file_id
    await requireActiveAttempt()
    const etag = await putFile(ticket.upload_url, ticket.content_type, file)
    await requireActiveAttempt()
    await confirmFileUpload(ticket.file_id, etag)
    await requireActiveAttempt()
    attempt.ready = true
  }
  return attempt.fileId!
}

function openCreate(event: MouseEvent) {
  rememberFocus(event.currentTarget)
  formError.value = ''
  uploadAttempt = null
  createOpen.value = true
}

function closeCreate() {
  if (saving.value) return
  createOpen.value = false
  formError.value = ''
  void cleanupUploadAttempt()
  restoreFocus()
}

async function saveTemplate(input: DocumentTemplateFormInput) {
  saving.value = true
  formError.value = ''
  try {
    const fileId = await uploadTemplateFile(input.file)
    const created = await registry.create({ name: input.name, fileId })
    uploadAttempt = null
    createOpen.value = false
    showToast('Шаблон добавлен', `${created.name} готов к генерации документов.`)
    restoreFocus()
  } catch (error) {
    formError.value = actionErrorMessage(error, 'Не удалось создать шаблон.')
  } finally {
    saving.value = false
  }
}

async function openDetails(template: DocumentTemplate, event: MouseEvent) {
  const sequence = ++detailsSequence
  rememberFocus(event.currentTarget)
  selectedTemplate.value = template
  detailsRefreshing.value = true
  try {
    const fresh = await registry.retrieve(template.id)
    if (sequence !== detailsSequence || selectedTemplate.value?.id !== fresh.id) return
    selectedTemplate.value = fresh
    registry.replaceTemplate(fresh)
  } catch (error) {
    if (sequence !== detailsSequence) return
    showToast(
      'Карточка открыта из списка',
      documentErrorMessage(error, 'Не удалось обновить шаблон.'),
    )
  } finally {
    if (sequence === detailsSequence) detailsRefreshing.value = false
  }
}

function closeDetails() {
  if (rendering.value || deleting.value) return
  detailsSequence += 1
  selectedTemplate.value = null
  restoreFocus()
}

function openRender() {
  if (detailsRefreshing.value) return
  renderError.value = ''
  renderOpen.value = true
}

function closeRender() {
  if (rendering.value) return
  renderOpen.value = false
  renderError.value = ''
}

function renderedFilename(name: string) {
  const clean = name.replace(/[/\\\x00-\x1f\x7f]/g, '_').trim().slice(0, 150) || 'document'
  return clean.toLowerCase().endsWith('.docx') ? clean : `${clean}.docx`
}

async function renderDocument(values: DocumentRenderValues) {
  const template = selectedTemplate.value
  if (!template) return
  rendering.value = true
  renderError.value = ''
  try {
    const blob = await renderDocumentTemplate(template.id, values)
    const objectUrl = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = objectUrl
    link.download = renderedFilename(template.name)
    link.rel = 'noopener'
    document.body.append(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(objectUrl)
    showToast('Документ сформирован', `${link.download} отправлен на скачивание.`)
  } catch (error) {
    renderError.value = documentErrorMessage(error, 'Не удалось сформировать документ.')
  } finally {
    rendering.value = false
  }
}

function openDelete() {
  if (detailsRefreshing.value) return
  deleteError.value = ''
  deleteOpen.value = true
}

function closeDelete() {
  if (deleting.value) return
  deleteOpen.value = false
  deleteError.value = ''
}

async function confirmDelete() {
  const template = selectedTemplate.value
  if (!template) return
  deleting.value = true
  deleteError.value = ''
  try {
    await registry.remove(template.id)
    deleteOpen.value = false
    selectedTemplate.value = null
    showToast('Шаблон удалён', 'Исходный DOCX сохранён в файловом каталоге.')
    restoreFocus()
  } catch (error) {
    deleteError.value = documentErrorMessage(error, 'Не удалось удалить шаблон.')
  } finally {
    deleting.value = false
  }
}

onMounted(() => {
  disposed = false
  void retryPendingFileCleanup()
  void registry.loadPage(1)
})

onBeforeUnmount(() => {
  disposed = true
  detailsSequence += 1
  emit('busyChange', false)
  document.body.classList.remove('modal-open')
  void cleanupUploadAttempt()
  if (toastTimer) clearTimeout(toastTimer)
})
</script>

<template>
  <main id="content">
    <DocumentsRegistry
      :templates="registry.templates.value"
      :current-page="registry.currentPage.value"
      :pagination-summary="paginationSummary"
      :has-next="Boolean(registry.nextCursor.value)"
      :loading="registry.loading.value"
      :error="registry.loadError.value"
      @create="openCreate"
      @select="openDetails"
      @page="registry.pageTo"
      @retry="registry.loadPage(registry.currentPage.value)"
    />
  </main>

  <DocumentTemplateFormModal
    v-if="createOpen"
    :saving="saving"
    :error="formError"
    @close="closeCreate"
    @save="saveTemplate"
  />
  <DocumentTemplateDetailsModal
    v-if="selectedTemplate && !renderOpen && !deleteOpen"
    :template="selectedTemplate"
    :busy="rendering || deleting"
    :refreshing="detailsRefreshing"
    @close="closeDetails"
    @render="openRender"
    @remove="openDelete"
  />
  <DocumentRenderModal
    v-if="selectedTemplate && renderOpen"
    :template="selectedTemplate"
    :rendering="rendering"
    :error="renderError"
    @close="closeRender"
    @render="renderDocument"
  />
  <DocumentTemplateDeleteModal
    v-if="selectedTemplate && deleteOpen"
    :template="selectedTemplate"
    :deleting="deleting"
    :error="deleteError"
    @close="closeDelete"
    @confirm="confirmDelete"
  />
  <AppToast v-if="toastVisible" :title="toastTitle" :message="toastMessage" />
</template>
