<script setup lang="ts">
import { computed } from 'vue'
import {
  COURIER_BULK_LIMIT,
  type Courier,
  type CourierBulkAction,
  type PlatformStatus,
} from '../../types/courier'
import CourierFilters from './CourierFilters.vue'
import CourierPagination from './CourierPagination.vue'
import CourierTable from './CourierTable.vue'

const props = defineProps<{
  couriers: Courier[]
  filterSummary: string
  currentPage: number
  paginationSummary: string
  hasNext: boolean
  loading: boolean
  error: string
  selectedIds: string[]
  bulkBusy: boolean
}>()

const pageSelectedCount = computed(
  () => props.couriers.filter((courier) => props.selectedIds.includes(courier.id)).length,
)
const allPageSelected = computed(
  () => props.couriers.length > 0 && pageSelectedCount.value === props.couriers.length,
)
const selectionDisabled = computed(() => props.loading || props.bulkBusy || Boolean(props.error))
const pageSelectionDisabled = computed(
  () => selectionDisabled.value || !props.couriers.length || (
    !allPageSelected.value &&
    props.selectedIds.length + props.couriers.length - pageSelectedCount.value > COURIER_BULK_LIMIT
  ),
)

const searchQuery = defineModel<string>('searchQuery', { required: true })
const status = defineModel<PlatformStatus | ''>('status', { required: true })

defineEmits<{
  create: [event: MouseEvent]
  select: [courier: Courier, event: Event]
  page: [page: number]
  retry: []
  search: []
  toggle: [courier: Courier]
  togglePage: []
  clearSelection: []
  bulk: [action: CourierBulkAction, event: MouseEvent]
}>()
</script>

<template>
  <section class="section" data-od-id="couriers-registry">
    <div class="container">
      <div class="row-between page-heading">
        <div>
          <p class="eyebrow">Courier API</p>
          <h1 data-od-id="couriers-title">Курьеры</h1>
        </div>
        <button
          class="btn btn-primary"
          type="button"
          data-od-id="create-courier"
          :disabled="bulkBusy"
          @click="$emit('create', $event)"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
            <path d="M12 5v14M5 12h14" />
          </svg>
          Создать
        </button>
      </div>

      <CourierFilters
        v-model:search-query="searchQuery"
        v-model:status="status"
        :summary="filterSummary"
        :loading="loading || bulkBusy"
        @search="$emit('search')"
      />

      <div class="card" data-od-id="couriers-table-card">
        <div class="courier-bulk-toolbar" data-od-id="courier-bulk-toolbar">
          <label class="courier-page-selection">
            <input
              class="courier-checkbox"
              type="checkbox"
              :checked="allPageSelected"
              :indeterminate="pageSelectedCount > 0 && !allPageSelected"
              :disabled="pageSelectionDisabled"
              @change="$emit('togglePage')"
            />
            Выбрать страницу
          </label>
          <span class="meta" aria-live="polite">Выбрано: {{ selectedIds.length }} / {{ COURIER_BULK_LIMIT }}</span>
          <div v-if="selectedIds.length" class="courier-bulk-buttons">
            <button
              class="btn btn-secondary btn-compact"
              type="button"
              :disabled="selectionDisabled"
              @click="$emit('bulk', 'status', $event)"
            >
              Изменить статус
            </button>
            <button
              class="btn btn-danger btn-danger-ghost btn-compact"
              type="button"
              :disabled="selectionDisabled"
              @click="$emit('bulk', 'delete', $event)"
            >
              Удалить выбранных
            </button>
            <button
              class="btn btn-ghost btn-compact"
              type="button"
              :disabled="loading || bulkBusy"
              @click="$emit('clearSelection')"
            >
              Снять выбор
            </button>
          </div>
          <p class="courier-selection-note meta">
            Выбор сохраняется между страницами и сбрасывается при применении поиска или фильтра.
            Максимум — {{ COURIER_BULK_LIMIT }} курьеров.
          </p>
        </div>
        <div v-if="loading && !couriers.length" class="registry-state" aria-busy="true">
          <span class="spinner" aria-hidden="true"></span>
          <h2>Загружаем курьеров</h2>
          <p>Получаем данные из Courier API.</p>
        </div>
        <div v-else-if="error" class="registry-state registry-error" role="alert">
          <h2>Не удалось загрузить реестр</h2>
          <p>{{ error }}</p>
          <button class="btn btn-secondary" type="button" @click="$emit('retry')">
            Повторить
          </button>
        </div>
        <template v-else>
          <CourierTable
            :couriers="couriers"
            :selected-ids="selectedIds"
            :disabled="loading || bulkBusy"
            @select="(courier, event) => $emit('select', courier, event)"
            @toggle="$emit('toggle', $event)"
          />
          <CourierPagination
            :current-page="currentPage"
            :summary="paginationSummary"
            :can-next="hasNext"
            :loading="loading || bulkBusy"
            @page="$emit('page', $event)"
          />
        </template>
      </div>
    </div>
  </section>
</template>
