<script setup lang="ts">
import type { Courier, PlatformStatus } from '../../types/courier'
import CourierFilters from './CourierFilters.vue'
import CourierPagination from './CourierPagination.vue'
import CourierTable from './CourierTable.vue'

defineProps<{
  couriers: Courier[]
  filteredCount: number
  filterSummary: string
  currentPage: number
  pageCount: number
  paginationSummary: string
}>()

const searchQuery = defineModel<string>('searchQuery', { required: true })
const cityFilter = defineModel<string>('cityFilter', { required: true })
const statusFilter = defineModel<'all' | PlatformStatus>('statusFilter', { required: true })

defineEmits<{
  create: [event: MouseEvent]
  select: [courier: Courier, event: MouseEvent]
  page: [page: number]
}>()
</script>

<template>
  <section class="section" data-od-id="couriers-registry">
    <div class="container">
      <div class="row-between page-heading">
        <h1 data-od-id="couriers-title">Курьеры</h1>
        <button
          class="btn btn-primary"
          type="button"
          data-od-id="create-courier"
          @click="$emit('create', $event)"
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            aria-hidden="true"
          >
            <path d="M12 5v14M5 12h14" />
          </svg>
          Создать
        </button>
      </div>

      <CourierFilters
        v-model:search-query="searchQuery"
        v-model:city-filter="cityFilter"
        v-model:status-filter="statusFilter"
        :summary="filterSummary"
      />

      <div class="card" data-od-id="couriers-table-card">
        <CourierTable
          :couriers="couriers"
          @select="(courier, event) => $emit('select', courier, event)"
        />
        <CourierPagination
          :current-page="currentPage"
          :page-count="pageCount"
          :summary="paginationSummary"
          :has-results="filteredCount > 0"
          @page="$emit('page', $event)"
        />
      </div>
    </div>
  </section>
</template>
