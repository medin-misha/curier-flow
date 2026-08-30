<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  confirmFileUpload,
  deleteFile,
  getFileDetails,
  getFileDownloadUrl,
  putFile,
  requestFileUpload,
} from '../../api/files'
import { ApiError } from '../../api/client'
import { receiptErrorMessage } from '../../api/receipts'
import { useReceiptsRegistry } from '../../composables/useReceiptsRegistry'
import type { StoredFile } from '../../types/file'
import type { Receipt, ReceiptFormInput, ReceiptPatchInput } from '../../types/receipt'
import AppToast from '../ui/AppToast.vue'
import ReceiptDeleteModal from './ReceiptDeleteModal.vue'
import ReceiptDetailsModal from './ReceiptDetailsModal.vue'
import ReceiptFormModal from './ReceiptFormModal.vue'
import ReceiptsRegistry from './ReceiptsRegistry.vue'

interface UploadAttempt {
  signature: string
  fileId: string | null
  ready: boolean
}

const emit = defineEmits<{
  busyChange: [busy: boolean]
}>()

const cleanupStorageKey = 'mfs.finance.pending-file-cleanup'

const registry = useReceiptsRegistry()
const selectedReceipt = ref<Receipt | null>(null)
const selectedFile = ref<StoredFile | null>(null)
const createOpen = ref(false)
const editOpen = ref(false)
const deleteOpen = ref(false)
const saving = ref(false)
const deleting = ref(false)
const downloading = ref(false)
const formError = ref('')
const deleteError = ref('')
const fileError = ref('')
const fileLoading = ref(false)
const detailsRefreshing = ref(false)
const toastVisible = ref(false)
const toastTitle = ref('')
const toastMessage = ref('')
const lastFocused = ref<HTMLElement | null>(null)
const fileIdentities = new WeakMap<File, string>()
let uploadAttempt: UploadAttempt | null = null
let createSignature = ''
let createIdempotencyKey = ''
let detailsSequence = 0
let fileSequence = 0
let toastTimer: ReturnType<typeof setTimeout> | undefined
let disposed = false

const paginationSummary = computed(
  () => `Страница ${registry.currentPage.value} · записей ${registry.receipts.value.length}`,
)

watch([createOpen, editOpen, deleteOpen, selectedReceipt], () => {
  document.body.classList.toggle(
    'modal-open',
    createOpen.value || editOpen.value || deleteOpen.value || Boolean(selectedReceipt.value),
  )
})

watch(
  [saving, deleting],
  () => emit('busyChange', saving.value || deleting.value),
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
  return receiptErrorMessage(error, fallback)
}

function pendingCleanupIds() {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(cleanupStorageKey) ?? '[]') as unknown
    return Array.isArray(parsed) ? parsed.filter((value): value is string => typeof value === 'string') : []
  } catch {
    return []
  }
}

function updatePendingCleanup(fileId: string, pending: boolean) {
  try {
    const storage = window.localStorage
    const ids = new Set(pendingCleanupIds())
    if (pending) ids.add(fileId)
    else ids.delete(fileId)
    if (ids.size) storage.setItem(cleanupStorageKey, JSON.stringify([...ids]))
    else storage.removeItem(cleanupStorageKey)
  } catch {
    // Очистка всё равно выполняется сразу; хранилище нужно только для повторной попытки.
  }
}

async function cleanupFile(fileId: string) {
  updatePendingCleanup(fileId, true)
  try {
    await deleteFile(fileId)
    updatePendingCleanup(fileId, false)
    return true
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
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

function resetCreateCommand() {
  createSignature = ''
  createIdempotencyKey = ''
}

function commandKey(fileId: string, amount: string, date: string) {
  const signature = JSON.stringify({ fileId, amount, date })
  if (signature !== createSignature) {
    createSignature = signature
    createIdempotencyKey = crypto.randomUUID()
  }
  return createIdempotencyKey
}

async function uploadReceiptFile(file: File) {
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
  resetCreateCommand()
  uploadAttempt = null
  createOpen.value = true
}

function closeCreate() {
  if (saving.value) return
  createOpen.value = false
  formError.value = ''
  resetCreateCommand()
  void cleanupUploadAttempt()
  restoreFocus()
}

async function loadSelectedFile(fileId: string) {
  const sequence = ++fileSequence
  selectedFile.value = null
  fileError.value = ''
  fileLoading.value = true
  try {
    const file = await getFileDetails(fileId)
    if (sequence === fileSequence && selectedReceipt.value?.fileId === fileId) {
      selectedFile.value = file
    }
  } catch (error) {
    if (sequence === fileSequence) {
      fileError.value = receiptErrorMessage(error, 'Не удалось получить файл чека.')
    }
  } finally {
    if (sequence === fileSequence) fileLoading.value = false
  }
}

async function openDetails(receipt: Receipt, event: MouseEvent) {
  const sequence = ++detailsSequence
  rememberFocus(event.currentTarget)
  selectedReceipt.value = receipt
  selectedFile.value = null
  fileError.value = ''
  detailsRefreshing.value = true
  void loadSelectedFile(receipt.fileId)
  try {
    const fresh = await registry.retrieve(receipt.id)
    if (sequence !== detailsSequence || selectedReceipt.value?.id !== fresh.id) return
    selectedReceipt.value = fresh
    registry.replaceReceipt(fresh)
    if (fresh.fileId !== receipt.fileId) void loadSelectedFile(fresh.fileId)
  } catch (error) {
    if (sequence !== detailsSequence) return
    showToast('Карточка открыта из списка', receiptErrorMessage(error, 'Не удалось обновить чек.'))
  } finally {
    if (sequence === detailsSequence) detailsRefreshing.value = false
  }
}

function closeDetails() {
  if (saving.value || deleting.value) return
  detailsSequence += 1
  fileSequence += 1
  selectedReceipt.value = null
  selectedFile.value = null
  fileError.value = ''
  restoreFocus()
}

function openEdit() {
  if (detailsRefreshing.value) return
  formError.value = ''
  uploadAttempt = null
  editOpen.value = true
}

function closeEdit() {
  if (saving.value) return
  editOpen.value = false
  formError.value = ''
  void cleanupUploadAttempt()
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

async function saveReceipt(input: ReceiptFormInput) {
  saving.value = true
  formError.value = ''
  try {
    if (createOpen.value && input.file) {
      const fileId = await uploadReceiptFile(input.file)
      const created = await registry.create(
        { fileId, amount: input.amount, date: input.date },
        commandKey(fileId, input.amount, input.date),
      )
      uploadAttempt = null
      createOpen.value = false
      resetCreateCommand()
      showToast('Чек добавлен', `${created.amount} Kč учтено в расходах.`)
      restoreFocus()
      return
    }

    const current = selectedReceipt.value
    if (!editOpen.value || !current) return
    const patch: ReceiptPatchInput = {}
    if (input.amount !== current.amount) patch.amount = input.amount
    if (input.date !== current.date) patch.date = input.date
    if (input.file) patch.fileId = await uploadReceiptFile(input.file)
    if (!Object.keys(patch).length) {
      editOpen.value = false
      return
    }

    const previousFileId = current.fileId
    const updated = await registry.update(current.id, patch)
    selectedReceipt.value = updated
    uploadAttempt = null
    editOpen.value = false
    await loadSelectedFile(updated.fileId)
    let cleanupFailed = false
    if (patch.fileId && patch.fileId !== previousFileId) {
      cleanupFailed = !(await cleanupFile(previousFileId))
    }
    showToast(
      'Чек обновлён',
      cleanupFailed
        ? 'Изменения сохранены, но старый файл не удалось удалить.'
        : `${updated.amount} Kč · изменения сохранены.`,
    )
  } catch (error) {
    formError.value = actionErrorMessage(error, 'Не удалось сохранить чек.')
  } finally {
    saving.value = false
  }
}

async function confirmDelete() {
  const receipt = selectedReceipt.value
  if (!receipt) return
  deleting.value = true
  deleteError.value = ''
  try {
    await registry.remove(receipt.id)
    const fileDeleted = await cleanupFile(receipt.fileId)
    deleteOpen.value = false
    selectedReceipt.value = null
    selectedFile.value = null
    showToast(
      'Чек удалён',
      fileDeleted ? `${receipt.amount} Kč удалено из реестра.` : 'Чек удалён, но файл не удалось очистить.',
    )
    restoreFocus()
  } catch (error) {
    deleteError.value = receiptErrorMessage(error, 'Не удалось удалить чек.')
  } finally {
    deleting.value = false
  }
}

async function downloadFile() {
  const file = selectedFile.value
  if (!file || downloading.value) return
  downloading.value = true
  try {
    const downloadUrl = await getFileDownloadUrl(file.id)
    if (!downloadUrl) throw new Error('Файл ещё не готов к скачиванию.')
    const link = document.createElement('a')
    link.href = downloadUrl
    link.download = file.originalName
    link.rel = 'noopener'
    link.click()
  } catch (error) {
    showToast('Не удалось скачать чек', actionErrorMessage(error, 'Повторите попытку.'))
  } finally {
    downloading.value = false
  }
}

onMounted(() => {
  disposed = false
  void retryPendingFileCleanup()
  void Promise.all([registry.loadPage(1), registry.loadStats()])
})

onBeforeUnmount(() => {
  disposed = true
  detailsSequence += 1
  fileSequence += 1
  emit('busyChange', false)
  document.body.classList.remove('modal-open')
  void cleanupUploadAttempt()
  if (toastTimer) clearTimeout(toastTimer)
})
</script>

<template>
  <main id="content">
    <ReceiptsRegistry
      :receipts="registry.receipts.value"
      :stats="registry.yearlyStats.value"
      :current-page="registry.currentPage.value"
      :pagination-summary="paginationSummary"
      :has-next="Boolean(registry.nextCursor.value)"
      :loading="registry.loading.value"
      :error="registry.loadError.value"
      :stats-loading="registry.statsLoading.value"
      :stats-error="registry.statsError.value"
      @create="openCreate"
      @select="openDetails"
      @page="registry.pageTo"
      @retry="registry.loadPage(registry.currentPage.value)"
      @retry-stats="registry.loadStats"
    />
  </main>

  <ReceiptFormModal v-if="createOpen" :saving="saving" :error="formError" @close="closeCreate" @save="saveReceipt" />
  <ReceiptDetailsModal
    v-if="selectedReceipt && !editOpen && !deleteOpen"
    :receipt="selectedReceipt"
    :file="selectedFile"
    :file-loading="fileLoading"
    :file-error="fileError"
    :busy="saving || deleting"
    :refreshing="detailsRefreshing"
    :downloading="downloading"
    @close="closeDetails"
    @edit="openEdit"
    @remove="openDelete"
    @download="downloadFile"
    @retry-file="loadSelectedFile(selectedReceipt.fileId)"
  />
  <ReceiptFormModal
    v-if="selectedReceipt && editOpen"
    :receipt="selectedReceipt"
    :saving="saving"
    :error="formError"
    @close="closeEdit"
    @save="saveReceipt"
  />
  <ReceiptDeleteModal
    v-if="selectedReceipt && deleteOpen"
    :receipt="selectedReceipt"
    :deleting="deleting"
    :error="deleteError"
    @close="closeDelete"
    @confirm="confirmDelete"
  />
  <AppToast v-if="toastVisible" :title="toastTitle" :message="toastMessage" />
</template>
