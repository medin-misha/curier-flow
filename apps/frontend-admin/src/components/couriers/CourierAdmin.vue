<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  addCourierDocument,
  createCourier,
  deleteCourier,
  getCourier,
  listCouriers,
  updateCourier,
  updateCourierPlatformStatus,
} from '../../api/couriers'
import { apiErrorMessage } from '../../api/client'
import { getFileDownloadUrl, getFilePreviewUrl } from '../../api/files'
import { useCourierBulkActions } from '../../composables/useCourierBulkActions'
import type {
  Courier,
  CourierBulkAction,
  CourierBulkStatusInput,
  CourierCreateInput,
  CourierDocument,
  CourierDocumentCreateInput,
  CourierFile,
  CourierFormValues,
  CourierPlatform,
  CourierUpdateInput,
  PlatformStatus,
} from '../../types/courier'
import AppToast from '../ui/AppToast.vue'
import CourierBulkModal from './CourierBulkModal.vue'
import CourierCreateModal from './CourierCreateModal.vue'
import CourierDeleteModal from './CourierDeleteModal.vue'
import CourierDetailsModal from './CourierDetailsModal.vue'
import CourierEditModal from './CourierEditModal.vue'
import CourierRegistry from './CourierRegistry.vue'

const PAGE_SIZE = 5

const emit = defineEmits<{ busyChange: [busy: boolean] }>()
const bulk = useCourierBulkActions()
const bulkAction = ref<CourierBulkAction | null>(null)
const bulkRefreshing = ref(false)
const bulkBusy = computed(() => bulk.busy.value || bulkRefreshing.value)
watch(bulkBusy, (busy) => emit('busyChange', busy))

const couriers = ref<Courier[]>([])
const searchQuery = ref('')
const statusFilter = ref<PlatformStatus | ''>('')
const appliedQuery = ref('')
const appliedStatus = ref<PlatformStatus | ''>('')
const currentPage = ref(1)
const cursors = ref<Array<string | null>>([null])
const nextCursor = ref<string | null>(null)
const loading = ref(false)
const loadError = ref('')
const createOpen = ref(false)
const editOpen = ref(false)
const editField = ref<keyof CourierFormValues | null>(null)
const deleteOpen = ref(false)
const selectedCourier = ref<Courier | null>(null)
const creating = ref(false)
const saving = ref(false)
const deleting = ref(false)
const createError = ref('')
const editError = ref('')
const deleteError = ref('')
const addingDocument = ref(false)
const documentError = ref('')
const downloadingFileIds = ref<string[]>([])
const updatingPlatformIds = ref<string[]>([])
const previewUrls = ref<Record<string, string>>({})
const previewLoadingFileIds = ref<string[]>([])
const previewErrorFileIds = ref<string[]>([])
const toastVisible = ref(false)
const toastTitle = ref('')
const toastMessage = ref('')
const lastFocused = ref<HTMLElement | null>(null)
let toastTimer: ReturnType<typeof setTimeout> | undefined
let loadSequence = 0
let previewSequence = 0

const platformStatusLabels: Record<PlatformStatus, string> = {
  active: 'Активен',
  pending: 'Ожидает',
  inactive: 'Неактивен',
}

const filterSummary = computed(() => {
  const filters = []
  if (appliedQuery.value) filters.push(`Точное совпадение: ${appliedQuery.value}`)
  if (appliedStatus.value) {
    filters.push(`Статус: ${platformStatusLabels[appliedStatus.value]}`)
  }
  return filters.length ? filters.join(' · ') : 'Данные из Courier API'
})
const paginationSummary = computed(
  () => `Страница ${currentPage.value} · записей ${couriers.value.length}`,
)

watch([createOpen, editOpen, deleteOpen, selectedCourier, bulkAction], () => {
  document.body.classList.toggle(
    'modal-open',
    createOpen.value ||
      editOpen.value ||
      deleteOpen.value ||
      Boolean(selectedCourier.value) ||
      Boolean(bulkAction.value),
  )
})

function rememberFocus(trigger?: EventTarget | null) {
  lastFocused.value =
    trigger instanceof HTMLElement
      ? trigger
      : (document.activeElement as HTMLElement | null)
}

function restoreFocus() {
  void nextTick(() => {
    if (lastFocused.value?.isConnected) lastFocused.value.focus()
    else document.querySelector<HTMLElement>('[data-od-id="courier-bulk-toolbar"] input')?.focus()
  })
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

async function loadPage(page: number) {
  const cursor = cursors.value[page - 1]
  if (cursor === undefined) return

  const sequence = ++loadSequence
  currentPage.value = page
  loading.value = true
  loadError.value = ''
  try {
    const result = await listCouriers({
      cursor,
      limit: PAGE_SIZE,
      query: appliedQuery.value,
      status: appliedStatus.value,
    })
    if (sequence !== loadSequence) return
    couriers.value = result.items
    bulk.sync(result.items)
    nextCursor.value = result.nextCursor
  } catch (error) {
    if (sequence !== loadSequence) return
    loadError.value = apiErrorMessage(error, 'Не удалось получить список курьеров.')
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}

async function search() {
  if (bulkBusy.value || bulkAction.value) return
  bulk.clearSelection()
  appliedQuery.value = searchQuery.value.trim()
  appliedStatus.value = statusFilter.value
  cursors.value = [null]
  nextCursor.value = null
  currentPage.value = 1
  await loadPage(1)
}

async function pageTo(page: number) {
  if (page < 1 || loading.value || bulkBusy.value || bulkAction.value) return
  if (page === currentPage.value + 1) {
    if (!nextCursor.value) return
    cursors.value[page - 1] = nextCursor.value
  }
  await loadPage(page)
}

function openCreate(event: MouseEvent) {
  if (bulkBusy.value || bulkAction.value) return
  rememberFocus(event.currentTarget)
  selectedCourier.value = null
  createError.value = ''
  createOpen.value = true
}

function closeCreate() {
  if (creating.value) return
  createOpen.value = false
  restoreFocus()
}

function revokePreviewUrls(urls: Record<string, string>) {
  if (typeof URL.revokeObjectURL !== 'function') return
  Object.values(urls).forEach((url) => URL.revokeObjectURL(url))
}

function resetDocumentPreviews() {
  previewSequence += 1
  revokePreviewUrls(previewUrls.value)
  previewUrls.value = {}
  previewLoadingFileIds.value = []
  previewErrorFileIds.value = []
}

function isImageFile(file: CourierFile) {
  return file.contentType.toLowerCase().startsWith('image/')
}

async function loadDocumentPreviews(courier: Courier) {
  const imageFiles = courier.documentFiles
    .map((document) => document.file)
    .filter((file) => isImageFile(file) && file.status === 'ready')
  if (!imageFiles.length) return

  const sequence = previewSequence
  previewLoadingFileIds.value = imageFiles.map((file) => file.id)
  const results = await Promise.all(
    imageFiles.map(async (file) => {
      try {
        return { id: file.id, url: await getFilePreviewUrl(file.id), error: false }
      } catch {
        return { id: file.id, url: null, error: true }
      }
    }),
  )

  if (sequence !== previewSequence || selectedCourier.value?.id !== courier.id) {
    results.forEach((result) => {
      if (result.url && typeof URL.revokeObjectURL === 'function') {
        URL.revokeObjectURL(result.url)
      }
    })
    return
  }

  previewUrls.value = Object.fromEntries(
    results.flatMap((result) => (result.url ? [[result.id, result.url]] : [])),
  )
  previewErrorFileIds.value = results
    .filter((result) => result.error || !result.url)
    .map((result) => result.id)
  previewLoadingFileIds.value = []
}

async function submitCreate(input: CourierCreateInput) {
  creating.value = true
  createError.value = ''
  try {
    const created = await createCourier(input)
    createOpen.value = false
    bulk.clearSelection()
    searchQuery.value = ''
    statusFilter.value = ''
    appliedQuery.value = ''
    appliedStatus.value = ''
    cursors.value = [null]
    await loadPage(1)
    showToast('Курьер сохранён', `${created.fullName} добавлен в реестр.`)
    restoreFocus()
  } catch (error) {
    createError.value = apiErrorMessage(error, 'Не удалось создать курьера.')
  } finally {
    creating.value = false
  }
}

async function openDetails(courier: Courier, event: Event) {
  if (loading.value || bulkBusy.value || bulkAction.value) return
  rememberFocus(event.currentTarget)
  resetDocumentPreviews()
  selectedCourier.value = courier
  try {
    const fresh = await getCourier(courier.id)
    if (selectedCourier.value?.id === fresh.id) {
      selectedCourier.value = fresh
      bulk.sync([fresh])
      const index = couriers.value.findIndex((item) => item.id === fresh.id)
      if (index >= 0) couriers.value[index] = fresh
      void loadDocumentPreviews(fresh)
    }
  } catch (error) {
    void loadDocumentPreviews(courier)
    showToast(
      'Карточка открыта из списка',
      apiErrorMessage(error, 'Не удалось обновить данные профиля.'),
    )
  }
}

function closeDetails() {
  if (addingDocument.value) return
  selectedCourier.value = null
  resetDocumentPreviews()
  restoreFocus()
}

function withAddedDocument(courier: Courier, document: CourierDocument): Courier {
  const documentFiles = [...courier.documentFiles, document]
  const pending = documentFiles.filter((item) => item.reviewStatus === 'processing').length
  return {
    ...courier,
    documents: documentFiles.length,
    documentFiles,
    documentStatus: pending ? `${pending} на проверке` : 'Проверены',
  }
}

async function submitDocument(input: CourierDocumentCreateInput) {
  const courierId = selectedCourier.value?.id
  if (!courierId || addingDocument.value) return

  addingDocument.value = true
  documentError.value = ''
  try {
    const document = await addCourierDocument(courierId, input)
    if (selectedCourier.value?.id !== courierId) return

    const updated = withAddedDocument(selectedCourier.value, document)
    selectedCourier.value = updated
    const index = couriers.value.findIndex((courier) => courier.id === courierId)
    if (index >= 0) couriers.value[index] = withAddedDocument(couriers.value[index], document)

    resetDocumentPreviews()
    void loadDocumentPreviews(updated)
    showToast('Документ добавлен', `${document.file.originalName} добавлен в профиль.`)
  } catch (error) {
    documentError.value = apiErrorMessage(error, 'Не удалось добавить документ.')
  } finally {
    addingDocument.value = false
  }
}

async function downloadFile(file: CourierFile) {
  if (file.status !== 'ready' || downloadingFileIds.value.includes(file.id)) return

  downloadingFileIds.value.push(file.id)
  try {
    const downloadUrl = await getFileDownloadUrl(file.id)
    if (!downloadUrl) {
      showToast('Файл недоступен', `${file.originalName} ещё не готов к скачиванию.`)
      return
    }

    const link = document.createElement('a')
    link.href = downloadUrl
    link.download = file.originalName
    link.rel = 'noopener'
    link.hidden = true
    document.body.append(link)
    link.click()
    link.remove()
  } catch (error) {
    showToast(
      'Не удалось скачать файл',
      apiErrorMessage(error, `Повторите скачивание файла ${file.originalName}.`),
    )
  } finally {
    downloadingFileIds.value = downloadingFileIds.value.filter((id) => id !== file.id)
  }
}

function withUpdatedPlatform(courier: Courier, platform: CourierPlatform): Courier {
  return {
    ...courier,
    platforms: courier.platforms.map((item) =>
      item.id === platform.id ? platform : item,
    ),
  }
}

async function updatePlatformStatus(platform: CourierPlatform, status: PlatformStatus) {
  const courierId = selectedCourier.value?.id
  if (
    !courierId ||
    platform.status === status ||
    updatingPlatformIds.value.includes(platform.id)
  ) {
    return
  }

  updatingPlatformIds.value.push(platform.id)
  try {
    const updated = await updateCourierPlatformStatus(courierId, platform.id, status)
    if (selectedCourier.value?.id === courierId) {
      selectedCourier.value = withUpdatedPlatform(selectedCourier.value, updated)
    }

    const index = couriers.value.findIndex((courier) => courier.id === courierId)
    if (index >= 0) couriers.value[index] = withUpdatedPlatform(couriers.value[index], updated)
    bulk.sync(couriers.value)

    showToast(
      'Статус платформы изменён',
      `${updated.name}: ${platformStatusLabels[updated.status]}.`,
    )
  } catch (error) {
    showToast(
      'Не удалось изменить статус',
      apiErrorMessage(error, `Повторите изменение статуса ${platform.name}.`),
    )
  } finally {
    updatingPlatformIds.value = updatingPlatformIds.value.filter(
      (id) => id !== platform.id,
    )
  }
}

function openEdit(field?: keyof CourierFormValues) {
  if (addingDocument.value) return
  editError.value = ''
  editField.value = field ?? null
  editOpen.value = true
}

function closeEdit() {
  if (saving.value) return
  editOpen.value = false
  editField.value = null
}

async function submitEdit(input: CourierUpdateInput) {
  if (!selectedCourier.value) return
  saving.value = true
  editError.value = ''
  try {
    const updated = await updateCourier(selectedCourier.value.id, input)
    selectedCourier.value = updated
    const index = couriers.value.findIndex((courier) => courier.id === updated.id)
    if (index >= 0) couriers.value[index] = updated
    bulk.sync([updated])
    editOpen.value = false
    editField.value = null
    showToast('Изменения сохранены', `Профиль ${updated.fullName} обновлён.`)
  } catch (error) {
    editError.value = apiErrorMessage(error, 'Не удалось сохранить изменения.')
  } finally {
    saving.value = false
  }
}

function openDelete() {
  if (addingDocument.value) return
  deleteError.value = ''
  deleteOpen.value = true
}

function closeDelete() {
  if (deleting.value) return
  deleteOpen.value = false
}

async function confirmDelete() {
  if (!selectedCourier.value) return
  deleting.value = true
  deleteError.value = ''
  const deletedName = selectedCourier.value.fullName
  const deletedId = selectedCourier.value.id
  try {
    await deleteCourier(deletedId)
    bulk.forget(deletedId)
    deleteOpen.value = false
    selectedCourier.value = null
    resetDocumentPreviews()
    cursors.value = [null]
    currentPage.value = 1
    await loadPage(1)
    showToast('Курьер удалён', `Профиль ${deletedName} удалён из реестра.`)
    restoreFocus()
  } catch (error) {
    deleteError.value = apiErrorMessage(error, 'Не удалось удалить курьера.')
  } finally {
    deleting.value = false
  }
}

function toggleSelection(courier: Courier) {
  if (loading.value || bulkBusy.value || bulkAction.value) return
  bulk.toggle(courier)
}

function togglePageSelection() {
  if (loading.value || bulkBusy.value || bulkAction.value) return
  bulk.togglePage(couriers.value)
}

function openBulk(action: CourierBulkAction, event: MouseEvent) {
  if (loading.value || bulkBusy.value || !bulk.selected.value.length) return
  rememberFocus(event.currentTarget)
  bulk.error.value = ''
  bulkAction.value = action
}

function closeBulk() {
  if (bulkBusy.value) return
  bulkAction.value = null
  restoreFocus()
}

async function finishBulk(title: string, message: string) {
  bulkRefreshing.value = true
  bulkAction.value = null
  couriers.value = []
  cursors.value = [null]
  nextCursor.value = null
  try {
    await loadPage(1)
    showToast(title, message)
    restoreFocus()
  } finally {
    bulkRefreshing.value = false
  }
}

async function confirmBulkDelete() {
  if (bulkAction.value !== 'delete' || bulkBusy.value) return
  const result = await bulk.remove()
  if (result) await finishBulk('Курьеры удалены', `Удалено профилей: ${result.deletedCount}.`)
}

async function confirmBulkStatus(input: CourierBulkStatusInput) {
  if (bulkAction.value !== 'status' || bulkBusy.value) return
  const result = await bulk.updateStatus(input)
  if (result) {
    await finishBulk(
      'Статусы платформы обновлены',
      `Изменено: ${result.updatedCount}. Уже имели нужный статус: ${result.unchangedCount}.`,
    )
  }
}

onMounted(() => {
  void loadPage(1)
})

onBeforeUnmount(() => {
  emit('busyChange', false)
  document.body.classList.remove('modal-open')
  revokePreviewUrls(previewUrls.value)
  if (toastTimer) clearTimeout(toastTimer)
})
</script>

<template>
  <main id="content">
    <CourierRegistry
      v-model:search-query="searchQuery"
      v-model:status="statusFilter"
      :couriers="couriers"
      :filter-summary="filterSummary"
      :current-page="currentPage"
      :pagination-summary="paginationSummary"
      :has-next="Boolean(nextCursor)"
      :loading="loading"
      :error="loadError"
      :selected-ids="bulk.selectedIds.value"
      :bulk-busy="bulkBusy"
      @create="openCreate"
      @select="openDetails"
      @page="pageTo"
      @retry="loadPage(currentPage)"
      @search="search"
      @toggle="toggleSelection"
      @toggle-page="togglePageSelection"
      @clear-selection="bulk.clearSelection"
      @bulk="openBulk"
    />
  </main>

  <CourierBulkModal
    v-if="bulkAction"
    :action="bulkAction"
    :couriers="bulk.selected.value"
    :busy="bulkBusy"
    :error="bulk.error.value"
    @close="closeBulk"
    @delete="confirmBulkDelete"
    @status="confirmBulkStatus"
    @clear-error="bulk.error.value = ''"
  />
  <CourierCreateModal
    v-if="createOpen"
    :saving="creating"
    :error="createError"
    @close="closeCreate"
    @submit="submitCreate"
  />
  <CourierDetailsModal
    v-if="selectedCourier && !editOpen && !deleteOpen"
    :courier="selectedCourier"
    :downloading-file-ids="downloadingFileIds"
    :updating-platform-ids="updatingPlatformIds"
    :preview-urls="previewUrls"
    :preview-loading-file-ids="previewLoadingFileIds"
    :preview-error-file-ids="previewErrorFileIds"
    :adding-document="addingDocument"
    :document-error="documentError"
    @close="closeDetails"
    @download="downloadFile"
    @add-document="submitDocument"
    @clear-document-error="documentError = ''"
    @edit="openEdit"
    @copied="showToast('Скопировано', `${$event} скопировано в буфер обмена.`)"
    @copy-error="showToast('Не удалось скопировать', `Поле «${$event}» не скопировано.`)"
    @delete="openDelete"
    @update-platform="updatePlatformStatus"
  />
  <CourierEditModal
    v-if="selectedCourier && editOpen"
    :courier="selectedCourier"
    :saving="saving"
    :error="editError"
    :focus-field="editField"
    @close="closeEdit"
    @save="submitEdit"
  />
  <CourierDeleteModal
    v-if="selectedCourier && deleteOpen"
    :courier="selectedCourier"
    :deleting="deleting"
    :error="deleteError"
    @close="closeDelete"
    @confirm="confirmDelete"
  />
  <AppToast
    v-if="toastVisible"
    :title="toastTitle"
    :message="toastMessage"
  />
</template>
