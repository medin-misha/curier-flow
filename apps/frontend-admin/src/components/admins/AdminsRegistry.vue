<script setup lang="ts">
import type { Admin } from '../../types/admin'
import AdminPagination from './AdminPagination.vue'
import AdminsTable from './AdminsTable.vue'

defineProps<{
  admins: Admin[]
  currentAdminId: string
  currentPage: number
  paginationSummary: string
  hasNext: boolean
  loading: boolean
  error: string
}>()

defineEmits<{
  create: [event: MouseEvent]
  select: [admin: Admin, event: MouseEvent]
  page: [page: number]
  retry: []
}>()
</script>

<template>
  <section class="section" data-od-id="admins-registry">
    <div class="container">
      <div class="row-between page-heading">
        <div>
          <p class="eyebrow">Admin API</p>
          <h1 data-od-id="admins-title">Администраторы</h1>
        </div>
        <button class="btn btn-primary" type="button" data-od-id="create-admin" @click="$emit('create', $event)">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
            <path d="M12 5v14M5 12h14" />
          </svg>
          Создать
        </button>
      </div>

      <div class="card" data-od-id="admins-table-card">
        <div v-if="loading && !admins.length" class="registry-state" aria-busy="true">
          <span class="spinner" aria-hidden="true"></span>
          <h2>Загружаем администраторов</h2>
          <p>Получаем учётные записи из Admin API.</p>
        </div>
        <div v-else-if="error" class="registry-state registry-error" role="alert">
          <h2>Не удалось загрузить реестр</h2>
          <p>{{ error }}</p>
          <button class="btn btn-secondary" type="button" @click="$emit('retry')">Повторить</button>
        </div>
        <template v-else>
          <AdminsTable
            :admins="admins"
            :current-admin-id="currentAdminId"
            @select="(admin, event) => $emit('select', admin, event)"
          />
          <AdminPagination
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
