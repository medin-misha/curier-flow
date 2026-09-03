<script setup lang="ts">
import type { Receipt, ReceiptTag, ReceiptYearSummary } from '../../types/receipt'
import AdminPagination from '../admins/AdminPagination.vue'
import ReceiptYearlyStats from './ReceiptYearlyStats.vue'
import ReceiptsTable from './ReceiptsTable.vue'

defineProps<{
  receipts: Receipt[]
  stats: ReceiptYearSummary[]
  tags: ReceiptTag[]
  selectedTagId: string | null
  tagsLoading: boolean
  currentPage: number
  paginationSummary: string
  hasNext: boolean
  loading: boolean
  error: string
  statsLoading: boolean
  statsError: string
}>()

defineEmits<{
  create: [event: MouseEvent]
  select: [receipt: Receipt, event: MouseEvent]
  page: [page: number]
  retry: []
  retryStats: []
  filterTag: [tagId: string | null]
  manageTags: [event: MouseEvent]
}>()
</script>

<template>
  <section class="section" data-od-id="finance-registry">
    <div class="container">
      <div class="row-between page-heading">
        <div>
          <p class="eyebrow">Finance API</p>
          <h1 data-od-id="finance-title">Чеки и расходы</h1>
        </div>
        <button class="btn btn-primary" type="button" data-od-id="create-receipt" @click="$emit('create', $event)">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
            <path d="M12 5v14M5 12h14" />
          </svg>
          Добавить чек
        </button>
      </div>

      <ReceiptYearlyStats
        :stats="stats"
        :loading="statsLoading"
        :error="statsError"
        @retry="$emit('retryStats')"
      />

      <div class="finance-registry-heading">
        <div>
          <p class="eyebrow">Реестр</p>
          <h2>Все чеки</h2>
        </div>
        <div class="finance-registry-actions">
          <label class="finance-tag-filter">
            <span>Тип расхода</span>
            <select
              class="select"
              :value="selectedTagId ?? ''"
              :disabled="loading || tagsLoading"
              data-od-id="receipt-tag-filter"
              @change="$emit('filterTag', ($event.target as HTMLSelectElement).value || null)"
            >
              <option value="">Все типы</option>
              <option v-for="tag in tags" :key="tag.id" :value="tag.id">{{ tag.name }}</option>
            </select>
          </label>
          <button class="btn btn-secondary" type="button" data-od-id="manage-receipt-tags" @click="$emit('manageTags', $event)">
            Управление тегами
          </button>
        </div>
      </div>
      <div class="card" data-od-id="receipts-table-card">
        <div v-if="loading && !receipts.length" class="registry-state" aria-busy="true">
          <span class="spinner" aria-hidden="true"></span>
          <h2>Загружаем чеки</h2>
          <p>Получаем реестр расходов из Finance API.</p>
        </div>
        <div v-else-if="error" class="registry-state registry-error" role="alert">
          <h2>Не удалось загрузить реестр</h2>
          <p>{{ error }}</p>
          <button class="btn btn-secondary" type="button" @click="$emit('retry')">Повторить</button>
        </div>
        <template v-else>
          <ReceiptsTable :receipts="receipts" :tags="tags" @select="(receipt, event) => $emit('select', receipt, event)" />
          <AdminPagination
            :current-page="currentPage"
            :summary="paginationSummary"
            :can-next="hasNext"
            :loading="loading"
            entity-label="чеков"
            data-od-id="receipts-pagination"
            @page="$emit('page', $event)"
          />
        </template>
      </div>
    </div>
  </section>
</template>
