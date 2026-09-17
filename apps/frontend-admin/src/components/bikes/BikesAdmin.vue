<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { getCourier } from '../../api/couriers'
import {
  confirmFileUpload,
  deleteFile,
  getFileDownloadUrl,
  putFile,
  requestFileUpload,
} from '../../api/files'
import {
  attachTransportContract,
  closeTransportRental,
  createTransport,
  createTransportComponent,
  createTransportRental,
  deleteTransport,
  deleteTransportComponent,
  getTransport,
  listTransportRentals,
  transportErrorMessage,
  updateTransport,
  updateTransportComponent,
  updateTransportRentalPayment,
} from '../../api/transports'
import { useTransportRegistry } from '../../composables/useTransportRegistry'
import type {
  Transport,
  TransportComponent,
  TransportComponentInput,
  TransportInput,
  TransportListItem,
  TransportPaymentType,
  TransportRental,
  TransportRentalInput,
} from '../../types/transport'
import AppToast from '../ui/AppToast.vue'
import BikesRegistry from './BikesRegistry.vue'
import ComponentFormModal from './ComponentFormModal.vue'
import ConfirmActionModal from './ConfirmActionModal.vue'
import ContractAttachModal from './ContractAttachModal.vue'
import RentalFormModal from './RentalFormModal.vue'
import RentalPaymentFormModal from './RentalPaymentFormModal.vue'
import { transportPaymentLabel } from './transportPayment'
import TransportDetailsModal from './TransportDetailsModal.vue'
import TransportFormModal from './TransportFormModal.vue'

type Dialog =
  | { type: 'create-transport' }
  | { type: 'edit-transport' }
  | { type: 'delete-transport' }
  | { type: 'create-component' }
  | { type: 'edit-component'; component: TransportComponent }
  | { type: 'delete-component'; component: TransportComponent }
  | { type: 'create-rental' }
  | { type: 'close-rental'; rental: TransportRental }
  | { type: 'edit-rental-payment'; rental: TransportRental }
  | { type: 'contract'; rental: TransportRental }

interface ContractAttempt {
  signature: string
  key: string
  fileId: string | null
  ready: boolean
}

const registry = useTransportRegistry()
const selectedTransport = ref<Transport | null>(null)
const rentals = ref<TransportRental[]>([])
const nextRentalCursor = ref<string | null>(null)
const rentalLoading = ref(false)
const courierNames = reactive<Record<string, string>>({})
const dialog = ref<Dialog | null>(null)
const busy = ref(false)
const actionError = ref('')
const downloadingFileIds = ref<string[]>([])
const toastVisible = ref(false)
const toastTitle = ref('')
const toastMessage = ref('')
const lastFocused = ref<HTMLElement | null>(null)
let toastTimer: ReturnType<typeof setTimeout> | undefined
let detailSequence = 0
let rentalSequence = 0
let commandSignature = ''
let commandIdempotencyKey = ''
let contractAttempt: ContractAttempt | null = null
const fileIdentities = new WeakMap<File, string>()

const paginationSummary = computed(
  () => `Страница ${registry.currentPage.value} · записей ${registry.transports.value.length}`,
)
const confirmCopy = computed(() => {
  if (dialog.value?.type === 'delete-component') {
    return {
      title: 'Удалить позицию комплектации?',
      message: `${dialog.value.component.name} будет удалена из текущей комплектации.`,
      action: 'Удалить позицию',
    }
  }
  return {
    title: 'Удалить велосипед?',
    message: 'Комплектация и история без подписанных договоров будут удалены. Подписанный договор заблокирует операцию.',
    action: 'Удалить велосипед',
  }
})

watch([dialog, selectedTransport], () => {
  document.body.classList.toggle('modal-open', Boolean(dialog.value || selectedTransport.value))
})

function rememberFocus(trigger?: EventTarget | null) {
  lastFocused.value = trigger instanceof HTMLElement ? trigger : (document.activeElement as HTMLElement | null)
}

function restoreFocus() {
  void nextTick(() => lastFocused.value?.focus())
}

function showToast(title: string, message: string) {
  toastTitle.value = title
  toastMessage.value = message
  toastVisible.value = true
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => (toastVisible.value = false), 4_200)
}

function resetCommand() {
  commandSignature = ''
  commandIdempotencyKey = ''
}

function commandKey(payload: unknown) {
  const signature = JSON.stringify(payload)
  if (signature !== commandSignature) {
    commandSignature = signature
    commandIdempotencyKey = crypto.randomUUID()
  }
  return commandIdempotencyKey
}

function openDialog(next: Dialog, event?: Event) {
  if (event) rememberFocus(event.currentTarget)
  actionError.value = ''
  resetCommand()
  dialog.value = next
}

function closeDialog() {
  if (busy.value) return
  if (dialog.value?.type === 'contract' && contractAttempt?.fileId) {
    void deleteFile(contractAttempt.fileId).catch(() => undefined)
  }
  contractAttempt = null
  dialog.value = null
  actionError.value = ''
  resetCommand()
  if (!selectedTransport.value) restoreFocus()
}

async function hydrateCouriers(found: TransportRental[]) {
  const ids = [...new Set(found.map((rental) => rental.courierId))].filter((id) => !courierNames[id])
  await Promise.all(
    ids.map(async (id) => {
      try {
        courierNames[id] = (await getCourier(id)).fullName
      } catch {
        courierNames[id] = id
      }
    }),
  )
}

async function loadRentals(reset: boolean) {
  const transport = selectedTransport.value
  if (!transport || (!reset && rentalLoading.value)) return
  const sequence = reset ? ++rentalSequence : rentalSequence
  const transportId = transport.id
  rentalLoading.value = true
  try {
    const result = await listTransportRentals(transport.id, {
      cursor: reset ? null : nextRentalCursor.value,
      limit: 10,
    })
    if (sequence !== rentalSequence || selectedTransport.value?.id !== transportId) return
    rentals.value = reset ? result.items : [...rentals.value, ...result.items]
    nextRentalCursor.value = result.nextCursor
    await hydrateCouriers(result.items)
  } catch (error) {
    if (sequence === rentalSequence && selectedTransport.value?.id === transportId) {
      actionError.value = transportErrorMessage(error, 'Не удалось загрузить историю аренды.')
    }
  } finally {
    if (sequence === rentalSequence) rentalLoading.value = false
  }
}

async function openDetails(transport: TransportListItem, event: Event) {
  const sequence = ++detailSequence
  rememberFocus(event.currentTarget)
  actionError.value = ''
  try {
    const fresh = await getTransport(transport.id)
    if (sequence !== detailSequence) return
    selectedTransport.value = fresh
    registry.replaceTransport(fresh)
    rentals.value = []
    nextRentalCursor.value = null
    await loadRentals(true)
  } catch (error) {
    if (sequence !== detailSequence) return
    showToast('Не удалось открыть карточку', transportErrorMessage(error, 'Повторите попытку.'))
    restoreFocus()
  }
}

function closeDetails() {
  if (busy.value) return
  detailSequence += 1
  rentalSequence += 1
  rentalLoading.value = false
  selectedTransport.value = null
  rentals.value = []
  actionError.value = ''
  restoreFocus()
}

async function refreshSelected() {
  if (!selectedTransport.value) return
  const fresh = await getTransport(selectedTransport.value.id)
  selectedTransport.value = fresh
  registry.replaceTransport(fresh)
}

async function refreshRentalState() {
  await Promise.all([refreshSelected(), registry.reloadFirstPage()])
  rentals.value = []
  nextRentalCursor.value = null
  await loadRentals(true)
}

async function saveTransport(input: TransportInput) {
  busy.value = true
  actionError.value = ''
  try {
    if (dialog.value?.type === 'create-transport') {
      const created = await createTransport(input, commandKey(input))
      dialog.value = null
      await registry.reloadFirstPage()
      showToast('Велосипед добавлен', `${created.model} · ${created.serialNumber}`)
      restoreFocus()
    } else if (dialog.value?.type === 'edit-transport' && selectedTransport.value) {
      const updated = await updateTransport(selectedTransport.value.id, input, selectedTransport.value)
      selectedTransport.value = updated
      registry.replaceTransport(updated)
      dialog.value = null
      showToast('Велосипед обновлён', updated.serialNumber)
    }
    resetCommand()
  } catch (error) {
    actionError.value = transportErrorMessage(error, 'Не удалось сохранить велосипед.')
  } finally {
    busy.value = false
  }
}

async function saveComponent(input: TransportComponentInput) {
  if (!selectedTransport.value) return
  busy.value = true
  actionError.value = ''
  try {
    if (dialog.value?.type === 'create-component') {
      await createTransportComponent(selectedTransport.value.id, input, commandKey(input))
    } else if (dialog.value?.type === 'edit-component') {
      await updateTransportComponent(selectedTransport.value.id, dialog.value.component.id, input)
    }
    await refreshSelected()
    dialog.value = null
    resetCommand()
    showToast('Комплектация обновлена', input.name)
  } catch (error) {
    actionError.value = transportErrorMessage(error, 'Не удалось сохранить комплектацию.')
  } finally {
    busy.value = false
  }
}

async function confirmDelete() {
  if (!selectedTransport.value) return
  busy.value = true
  actionError.value = ''
  try {
    if (dialog.value?.type === 'delete-component') {
      const name = dialog.value.component.name
      await deleteTransportComponent(selectedTransport.value.id, dialog.value.component.id)
      await refreshSelected()
      dialog.value = null
      showToast('Позиция удалена', name)
    } else {
      const name = selectedTransport.value.model
      await deleteTransport(selectedTransport.value.id)
      dialog.value = null
      selectedTransport.value = null
      await registry.reloadFirstPage()
      showToast('Велосипед удалён', name)
      restoreFocus()
    }
  } catch (error) {
    actionError.value = transportErrorMessage(error, 'Не удалось выполнить удаление.')
  } finally {
    busy.value = false
  }
}

async function createRental(input: TransportRentalInput) {
  if (!selectedTransport.value) return
  busy.value = true
  actionError.value = ''
  try {
    await createTransportRental(selectedTransport.value.id, input, commandKey(input))
    dialog.value = null
    resetCommand()
    await refreshRentalState()
    showToast('Аренда сохранена', input.endedAt ? 'Исторический период добавлен.' : 'Велосипед выдан курьеру.')
  } catch (error) {
    actionError.value = transportErrorMessage(error, 'Не удалось сохранить аренду.')
  } finally {
    busy.value = false
  }
}

async function saveRentalPayment(paymentType: TransportPaymentType) {
  if (!selectedTransport.value || dialog.value?.type !== 'edit-rental-payment') return
  busy.value = true
  actionError.value = ''
  try {
    const updated = await updateTransportRentalPayment(selectedTransport.value.id, dialog.value.rental.id, paymentType)
    rentals.value = rentals.value.map((rental) => rental.id === updated.id ? updated : rental)
    if (selectedTransport.value.activeRental?.id === updated.id) {
      selectedTransport.value.activeRental = updated
    }
    dialog.value = null
    showToast('Тип оплаты сохранён', transportPaymentLabel(updated.paymentType))
  } catch (error) {
    actionError.value = transportErrorMessage(error, 'Не удалось сохранить тип оплаты.')
  } finally {
    busy.value = false
  }
}

async function closeRental(endedAt: string) {
  if (!selectedTransport.value || dialog.value?.type !== 'close-rental') return
  busy.value = true
  actionError.value = ''
  try {
    await closeTransportRental(selectedTransport.value.id, dialog.value.rental.id, endedAt, commandKey({ endedAt }))
    dialog.value = null
    resetCommand()
    await refreshRentalState()
    showToast('Аренда завершена', 'Велосипед снова доступен.')
  } catch (error) {
    actionError.value = transportErrorMessage(error, 'Не удалось завершить аренду.')
  } finally {
    busy.value = false
  }
}

async function attachContract(file: File) {
  if (!selectedTransport.value || dialog.value?.type !== 'contract') return
  busy.value = true
  actionError.value = ''
  let signature = fileIdentities.get(file)
  if (!signature) {
    signature = crypto.randomUUID()
    fileIdentities.set(file, signature)
  }
  if (!contractAttempt || contractAttempt.signature !== signature) {
    if (contractAttempt?.fileId) {
      await deleteFile(contractAttempt.fileId).catch(() => undefined)
    }
    contractAttempt = { signature, key: crypto.randomUUID(), fileId: null, ready: false }
  }
  const attempt = contractAttempt
  try {
    if (!attempt.ready) {
      if (attempt.fileId) await deleteFile(attempt.fileId).catch(() => undefined)
      const ticket = await requestFileUpload(file)
      attempt.fileId = ticket.file_id
      const etag = await putFile(ticket.upload_url, ticket.content_type, file)
      await confirmFileUpload(ticket.file_id, etag)
      attempt.ready = true
    }
    await attachTransportContract(selectedTransport.value.id, dialog.value.rental.id, attempt.fileId!, attempt.key)
    contractAttempt = null
    dialog.value = null
    await refreshRentalState()
    showToast('Договор приложен', file.name)
  } catch (error) {
    actionError.value = error instanceof Error && !(error as { status?: number }).status
      ? error.message
      : transportErrorMessage(error, 'Не удалось приложить договор.')
  } finally {
    busy.value = false
  }
}

async function downloadContract(rental: TransportRental) {
  if (!rental.file || downloadingFileIds.value.includes(rental.file.id)) return
  downloadingFileIds.value.push(rental.file.id)
  try {
    const url = await getFileDownloadUrl(rental.file.id)
    if (!url) throw new Error('Файл ещё не готов к скачиванию.')
    const link = document.createElement('a')
    link.href = url
    link.download = rental.file.originalName
    link.rel = 'noopener'
    link.click()
  } catch (error) {
    showToast('Не удалось скачать договор', error instanceof Error ? error.message : 'Повторите попытку.')
  } finally {
    downloadingFileIds.value = downloadingFileIds.value.filter((id) => id !== rental.file?.id)
  }
}

onMounted(() => void registry.loadPage(1))
onBeforeUnmount(() => {
  detailSequence += 1
  rentalSequence += 1
  if (contractAttempt?.fileId) void deleteFile(contractAttempt.fileId).catch(() => undefined)
  document.body.classList.remove('modal-open')
  if (toastTimer) clearTimeout(toastTimer)
})
</script>

<template>
  <main id="content"><BikesRegistry :transports="registry.transports.value" :filters="registry.draftFilters" :current-page="registry.currentPage.value" :pagination-summary="paginationSummary" :has-next="Boolean(registry.nextCursor.value)" :loading="registry.loading.value" :error="registry.loadError.value" @create="openDialog({ type: 'create-transport' }, $event)" @select="openDetails" @apply-filters="registry.applyFilters" @clear-filters="registry.clearFilters" @page="registry.pageTo" @retry="registry.loadPage(registry.currentPage.value)" /></main>

  <TransportDetailsModal v-if="selectedTransport && !dialog" :transport="selectedTransport" :rentals="rentals" :courier-names="courierNames" :rental-loading="rentalLoading" :rentals-next="Boolean(nextRentalCursor)" :busy="busy" :error="actionError" :downloading-file-ids="downloadingFileIds" @close="closeDetails" @edit="openDialog({ type: 'edit-transport' })" @delete="openDialog({ type: 'delete-transport' })" @add-component="openDialog({ type: 'create-component' })" @edit-component="openDialog({ type: 'edit-component', component: $event })" @delete-component="openDialog({ type: 'delete-component', component: $event })" @create-rental="openDialog({ type: 'create-rental' })" @close-rental="openDialog({ type: 'close-rental', rental: $event })" @edit-rental-payment="openDialog({ type: 'edit-rental-payment', rental: $event })" @attach-contract="openDialog({ type: 'contract', rental: $event })" @download-contract="downloadContract" @load-more-rentals="loadRentals(false)" />
  <TransportFormModal v-if="dialog?.type === 'create-transport' || dialog?.type === 'edit-transport'" :transport="dialog.type === 'edit-transport' ? selectedTransport : null" :saving="busy" :error="actionError" @close="closeDialog" @save="saveTransport" />
  <ComponentFormModal v-if="dialog?.type === 'create-component' || dialog?.type === 'edit-component'" :component="dialog.type === 'edit-component' ? dialog.component : null" :saving="busy" :error="actionError" @close="closeDialog" @save="saveComponent" />
  <RentalFormModal v-if="dialog?.type === 'create-rental' || dialog?.type === 'close-rental'" :rental="dialog.type === 'close-rental' ? dialog.rental : null" :require-historical="dialog.type === 'create-rental' && Boolean(selectedTransport?.activeRental)" :saving="busy" :error="actionError" @close="closeDialog" @create="createRental" @close-rental="closeRental" />
  <RentalPaymentFormModal v-if="dialog?.type === 'edit-rental-payment'" :rental="dialog.rental" :saving="busy" :error="actionError" @close="closeDialog" @save="saveRentalPayment" />
  <ContractAttachModal v-if="dialog?.type === 'contract'" :rental="dialog.rental" :saving="busy" :error="actionError" @close="closeDialog" @save="attachContract" />
  <ConfirmActionModal v-if="dialog?.type === 'delete-transport' || dialog?.type === 'delete-component'" :title="confirmCopy.title" :message="confirmCopy.message" :action="confirmCopy.action" :saving="busy" :error="actionError" @close="closeDialog" @confirm="confirmDelete" />
  <AppToast v-if="toastVisible" :title="toastTitle" :message="toastMessage" />
</template>
