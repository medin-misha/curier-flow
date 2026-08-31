<script setup lang="ts">
import type { Courier } from '../../types/courier'
import CourierFilters from './CourierFilters.vue'
import CourierPagination from './CourierPagination.vue'
import CourierTable from './CourierTable.vue'

defineProps<{
  couriers: Courier[]
  filterSummary: string
  currentPage: number
  paginationSummary: string
  hasNext: boolean
  loading: boolean
  error: string
}>()

const searchQuery = defineModel<string>('searchQuery', { required: true })

defineEmits<{
  create: [event: MouseEvent]
  select: [courier: Courier, event: Event]
  page: [page: number]
  retry: []
  search: []
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
        :summary="filterSummary"
        :loading="loading"
        @search="$emit('search')"
      />

      <div class="card" data-od-id="couriers-table-card">
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
            @select="(courier, event) => $emit('select', courier, event)"
          />
          <CourierPagination
            :current-page="currentPage"
            :summary="paginationSummary"
            :can-next="hasNext"
            :loading="loading"
            @page="$emit('page', $event)"
          />
        </template>
      </div>
    </div>
  </section>
</template>
