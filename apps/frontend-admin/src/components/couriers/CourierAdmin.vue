<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { createDemoCouriers } from '../../data/couriers'
import type { Courier, PlatformStatus } from '../../types/courier'
import AppToast from '../ui/AppToast.vue'
import CourierCreateModal from './CourierCreateModal.vue'
import CourierDetailsModal from './CourierDetailsModal.vue'
import CourierRegistry from './CourierRegistry.vue'

const PAGE_SIZE = 5

const couriers = ref(createDemoCouriers())
const searchQuery = ref('')
const cityFilter = ref('all')
const statusFilter = ref<'all' | PlatformStatus>('all')
const currentPage = ref(1)
const createOpen = ref(false)
const selectedCourier = ref<Courier | null>(null)
const toastVisible = ref(false)
const lastFocused = ref<HTMLElement | null>(null)
const ownedPreviewUrls = new Set<string>()
let toastTimer: ReturnType<typeof setTimeout> | undefined

const filteredCouriers = computed(() => {
  const query = searchQuery.value.trim().toLocaleLowerCase('ru')

  return couriers.value.filter((courier) => {
    const matchesQuery =
      !query ||
      [courier.fullName, courier.email, courier.phone].some((value) =>
        value.toLocaleLowerCase('ru').includes(query),
      )
    const matchesCity = cityFilter.value === 'all' || courier.city === cityFilter.value
    const matchesStatus =
      statusFilter.value === 'all' ||
      courier.platforms.some((platform) => platform.status === statusFilter.value)

    return matchesQuery && matchesCity && matchesStatus
  })
})

const pageCount = computed(() =>
  Math.max(1, Math.ceil(filteredCouriers.value.length / PAGE_SIZE)),
)
const pageStart = computed(() => (currentPage.value - 1) * PAGE_SIZE)
const visibleCouriers = computed(() =>
  filteredCouriers.value.slice(pageStart.value, pageStart.value + PAGE_SIZE),
)
const paginationSummary = computed(() => {
  const total = filteredCouriers.value.length
  const from = total ? pageStart.value + 1 : 0
  const to = Math.min(pageStart.value + PAGE_SIZE, total)
  return `${from}–${to} из ${total}`
})
const filterSummary = computed(() =>
  filteredCouriers.value.length === couriers.value.length
    ? 'Показаны все записи'
    : `Найдено: ${filteredCouriers.value.length}`,
)

watch([searchQuery, cityFilter, statusFilter], () => {
  currentPage.value = 1
})

watch(pageCount, (count) => {
  currentPage.value = Math.min(currentPage.value, count)
})

watch([createOpen, selectedCourier], ([isCreateOpen, courier]) => {
  document.body.classList.toggle('modal-open', isCreateOpen || Boolean(courier))
})

function pageTo(page: number) {
  currentPage.value = Math.min(Math.max(page, 1), pageCount.value)
}

function rememberFocus(trigger?: EventTarget | null) {
  lastFocused.value =
    trigger instanceof HTMLElement
      ? trigger
      : (document.activeElement as HTMLElement | null)
}

function restoreFocus() {
  void nextTick(() => lastFocused.value?.focus())
}

function openCreate(event: MouseEvent) {
  rememberFocus(event.currentTarget)
  selectedCourier.value = null
  createOpen.value = true
}

function closeCreate() {
  createOpen.value = false
  restoreFocus()
}

function openDetails(courier: Courier, event: MouseEvent) {
  rememberFocus(event.currentTarget)
  createOpen.value = false
  selectedCourier.value = courier
}

function closeDetails() {
  selectedCourier.value = null
  restoreFocus()
}

function showToast() {
  toastVisible.value = true
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => {
    toastVisible.value = false
  }, 4_200)
}

function addCourier(courier: Courier) {
  for (const document of courier.documentFiles) {
    if (document.file.previewUrl) ownedPreviewUrls.add(document.file.previewUrl)
  }

  couriers.value.unshift(courier)
  searchQuery.value = ''
  cityFilter.value = 'all'
  statusFilter.value = 'all'
  currentPage.value = 1
  closeCreate()
  showToast()
}

onBeforeUnmount(() => {
  document.body.classList.remove('modal-open')
  if (toastTimer) clearTimeout(toastTimer)
  ownedPreviewUrls.forEach((url) => URL.revokeObjectURL(url))
})
</script>

<template>
  <main id="content">
    <CourierRegistry
      v-model:search-query="searchQuery"
      v-model:city-filter="cityFilter"
      v-model:status-filter="statusFilter"
      :couriers="visibleCouriers"
      :filtered-count="filteredCouriers.length"
      :filter-summary="filterSummary"
      :current-page="currentPage"
      :page-count="pageCount"
      :pagination-summary="paginationSummary"
      @create="openCreate"
      @select="openDetails"
      @page="pageTo"
    />
  </main>

  <CourierCreateModal v-if="createOpen" @close="closeCreate" @created="addCourier" />
  <CourierDetailsModal
    v-if="selectedCourier"
    :courier="selectedCourier"
    @close="closeDetails"
  />
  <AppToast v-if="toastVisible" />
</template>
