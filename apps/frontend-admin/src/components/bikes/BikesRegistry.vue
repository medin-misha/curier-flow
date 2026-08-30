<script setup lang="ts">
import type { TransportFilters, TransportListItem } from '../../types/transport'
import AdminPagination from '../admins/AdminPagination.vue'

defineProps<{
  transports: TransportListItem[]
  filters: TransportFilters
  currentPage: number
  paginationSummary: string
  hasNext: boolean
  loading: boolean
  error: string
}>()

defineEmits<{
  create: [event: MouseEvent]
  select: [transport: TransportListItem, event: MouseEvent]
  applyFilters: []
  clearFilters: []
  page: [page: number]
  retry: []
}>()

function formatDate(value: string) {
  return new Intl.DateTimeFormat('ru-RU').format(new Date(value))
}
</script>

<template>
  <section class="section" data-od-id="bikes-registry">
    <div class="container">
      <div class="row-between page-heading">
        <div>
          <p class="eyebrow">Transport API</p>
          <h1 data-od-id="bikes-title">Велосипеды</h1>
        </div>
        <button class="btn btn-primary" type="button" data-od-id="create-bike" @click="$emit('create', $event)">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
          Добавить велосипед
        </button>
      </div>

      <form class="toolbar bikes-toolbar" @submit.prevent="$emit('applyFilters')">
        <input v-model="filters.type" class="input" type="text" maxlength="64" placeholder="Точный тип, например e-bike" aria-label="Тип транспорта" />
        <input v-model="filters.serialNumber" class="input num" type="text" maxlength="64" placeholder="Серийный номер" aria-label="Серийный номер" />
        <select v-model="filters.availability" class="select" aria-label="Доступность">
          <option value="">Любая доступность</option>
          <option value="available">Свободен</option>
          <option value="rented">Выдан</option>
        </select>
        <input v-model="filters.courierId" class="input num" type="text" placeholder="ID текущего курьера" aria-label="ID текущего курьера" />
        <button class="btn btn-secondary" type="submit" :disabled="loading">Применить</button>
        <button class="btn btn-ghost" type="button" :disabled="loading" @click="$emit('clearFilters')">Сбросить</button>
      </form>

      <div class="card" data-od-id="bikes-table-card">
        <div v-if="loading && !transports.length" class="registry-state" aria-busy="true">
          <span class="spinner" aria-hidden="true"></span><h2>Загружаем парк</h2><p>Получаем транспорт и его доступность.</p>
        </div>
        <div v-else-if="error" class="registry-state registry-error" role="alert">
          <h2>Не удалось загрузить парк</h2><p>{{ error }}</p><button class="btn btn-secondary" type="button" @click="$emit('retry')">Повторить</button>
        </div>
        <template v-else>
          <div class="table-shell">
            <table v-if="transports.length" class="ds-table bikes-table" data-od-id="bikes-table">
              <thead><tr><th>Велосипед</th><th>Серийный номер</th><th>Цвет</th><th>Ставка</th><th>Залог</th><th>Доступность</th><th>Обновлён</th><th><span class="visually-hidden">Действия</span></th></tr></thead>
              <tbody>
                <tr v-for="transport in transports" :key="transport.id" :data-od-id="`bike-row-${transport.id}`">
                  <td data-label="Велосипед"><div class="person"><strong>{{ transport.model }}</strong><span>{{ transport.type }}</span></div></td>
                  <td data-label="Серийный номер"><span class="num">{{ transport.serialNumber }}</span></td>
                  <td data-label="Цвет">{{ transport.color }}</td>
                  <td data-label="Ставка"><span class="num">{{ transport.rentalPrice }} Kč</span></td>
                  <td data-label="Залог"><span class="num">{{ transport.depositRequired ? `${transport.depositAmount} Kč` : 'Без залога' }}</span></td>
                  <td data-label="Доступность"><span class="status" :class="transport.isAvailable ? 'status-ok' : 'status-warn'">{{ transport.isAvailable ? 'Свободен' : 'Выдан' }}</span></td>
                  <td data-label="Обновлён"><span class="num">{{ formatDate(transport.updatedAt) }}</span></td>
                  <td data-label="Действия"><button class="table-action" type="button" :aria-label="`Открыть ${transport.model}`" :data-od-id="`open-bike-${transport.id}`" @click="$emit('select', transport, $event)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="12" cy="5" r="1" /><circle cx="12" cy="12" r="1" /><circle cx="12" cy="19" r="1" /></svg></button></td>
                </tr>
              </tbody>
            </table>
            <div v-else class="empty-state"><h2>Велосипеды не найдены</h2><p>Измените точные фильтры или добавьте первый велосипед.</p></div>
          </div>
          <AdminPagination :current-page="currentPage" :summary="paginationSummary" :can-next="hasNext" :loading="loading" entity-label="велосипедов" data-od-id="bikes-pagination" @page="$emit('page', $event)" />
        </template>
      </div>
    </div>
  </section>
</template>
