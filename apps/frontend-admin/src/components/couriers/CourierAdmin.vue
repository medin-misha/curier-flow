<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  createCourier,
  deleteCourier,
  getCourier,
  listCouriers,
  updateCourier,
  updateCourierPlatformStatus,
} from '../../api/couriers'
import { apiErrorMessage } from '../../api/client'
import { getFileDownloadUrl } from '../../api/files'
import type {
  Courier,
  CourierCreateInput,
  CourierFile,
  CourierPlatform,
  CourierUpdateInput,
  PlatformStatus,
} from '../../types/courier'
import AppToast from '../ui/AppToast.vue'
import CourierCreateModal from './CourierCreateModal.vue'
import CourierDeleteModal from './CourierDeleteModal.vue'
import CourierDetailsModal from './CourierDetailsModal.vue'
import CourierEditModal from './CourierEditModal.vue'
import CourierRegistry from './CourierRegistry.vue'

const PAGE_SIZE = 5

const couriers = ref<Courier[]>([])
const searchQuery = ref('')
const appliedQuery = ref('')
const currentPage = ref(1)
const cursors = ref<Array<string | null>>([null])
const nextCursor = ref<string | null>(null)
const loading = ref(false)
const loadError = ref('')
const createOpen = ref(false)
const editOpen = ref(false)
const deleteOpen = ref(false)
const selectedCourier = ref<Courier | null>(null)
const creating = ref(false)
const saving = ref(false)
const deleting = ref(false)
const createError = ref('')
const editError = ref('')
const deleteError = ref('')
const downloadingFileIds = ref<string[]>([])
const updatingPlatformIds = ref<string[]>([])
const toastVisible = ref(false)
const toastTitle = ref('')
const toastMessage = ref('')
const lastFocused = ref<HTMLElement | null>(null)
let toastTimer: ReturnType<typeof setTimeout> | undefined
let loadSequence = 0

const platformStatusLabels: Record<PlatformStatus, string> = {
  active: 'Активен',
  pending: 'Ожидает',
  inactive: 'Неактивен',
}

const filterSummary = computed(() =>
  appliedQuery.value
    ? `Точное совпадение: ${appliedQuery.value}`
    : 'Данные из Courier API',
)
const paginationSummary = computed(
  () => `Страница ${currentPage.value} · записей ${couriers.value.length}`,
)

watch([createOpen, editOpen, deleteOpen, selectedCourier], () => {
  document.body.classList.toggle(
    'modal-open',
    createOpen.value || editOpen.value || deleteOpen.value || Boolean(selectedCourier.value),
  )
})

function rememberFocus(trigger?: EventTarget | null) {
  lastFocused.value =
    trigger instanceof HTMLElement
      ? trigger
      : (document.activeElement as HTMLElement | null)
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
    })
    if (sequence !== loadSequence) return
    couriers.value = result.items
    nextCursor.value = result.nextCursor
  } catch (error) {
    if (sequence !== loadSequence) return
    loadError.value = apiErrorMessage(error, 'Не удалось получить список курьеров.')
  } finally {
    if (sequence === loadSequence) loading.value = false
  }
}

async function search() {
  appliedQuery.value = searchQuery.value.trim()
  cursors.value = [null]
  nextCursor.value = null
  currentPage.value = 1
  await loadPage(1)
}

async function pageTo(page: number) {
  if (page < 1) return
  if (page === currentPage.value + 1) {
    if (!nextCursor.value) return
    cursors.value[page - 1] = nextCursor.value
  }
  await loadPage(page)
}

function openCreate(event: MouseEvent) {
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

async function submitCreate(input: CourierCreateInput) {
  creating.value = true
  createError.value = ''
  try {
    const created = await createCourier(input)
    createOpen.value = false
    searchQuery.value = ''
    appliedQuery.value = ''
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
  rememberFocus(event.currentTarget)
  selectedCourier.value = courier
  try {
    const fresh = await getCourier(courier.id)
    if (selectedCourier.value?.id === fresh.id) {
      selectedCourier.value = fresh
      const index = couriers.value.findIndex((item) => item.id === fresh.id)
      if (index >= 0) couriers.value[index] = fresh
    }
  } catch (error) {
    showToast(
      'Карточка открыта из списка',
      apiErrorMessage(error, 'Не удалось обновить данные профиля.'),
    )
  }
}

function closeDetails() {
  selectedCourier.value = null
  restoreFocus()
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

function openEdit() {
  editError.value = ''
  editOpen.value = true
}

function closeEdit() {
  if (saving.value) return
  editOpen.value = false
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
    editOpen.value = false
    showToast('Изменения сохранены', `Профиль ${updated.fullName} обновлён.`)
  } catch (error) {
    editError.value = apiErrorMessage(error, 'Не удалось сохранить изменения.')
  } finally {
    saving.value = false
  }
}

function openDelete() {
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
  try {
    await deleteCourier(selectedCourier.value.id)
    deleteOpen.value = false
    selectedCourier.value = null
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

onMounted(() => {
  void loadPage(1)
})

onBeforeUnmount(() => {
  document.body.classList.remove('modal-open')
  if (toastTimer) clearTimeout(toastTimer)
})
</script>

<template>
  <main id="content">
    <CourierRegistry
      v-model:search-query="searchQuery"
      :couriers="couriers"
      :filter-summary="filterSummary"
      :current-page="currentPage"
      :pagination-summary="paginationSummary"
      :has-next="Boolean(nextCursor)"
      :loading="loading"
      :error="loadError"
      @create="openCreate"
      @select="openDetails"
      @page="pageTo"
      @retry="loadPage(currentPage)"
      @search="search"
    />
  </main>

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
    @close="closeDetails"
    @download="downloadFile"
    @edit="openEdit"
    @delete="openDelete"
    @update-platform="updatePlatformStatus"
  />
  <CourierEditModal
    v-if="selectedCourier && editOpen"
    :courier="selectedCourier"
    :saving="saving"
    :error="editError"
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
