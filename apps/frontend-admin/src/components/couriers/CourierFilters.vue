<script setup lang="ts">
import type { PlatformStatus } from '../../types/courier'

defineProps<{
  summary: string
}>()

const searchQuery = defineModel<string>('searchQuery', { required: true })
const cityFilter = defineModel<string>('cityFilter', { required: true })
const statusFilter = defineModel<'all' | PlatformStatus>('statusFilter', { required: true })
</script>

<template>
  <div class="toolbar" data-od-id="couriers-filters">
    <label class="control-wrap">
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="1.7"
        aria-hidden="true"
      >
        <circle cx="11" cy="11" r="6.5" />
        <path d="m16 16 4 4" />
      </svg>
      <span class="visually-hidden">Поиск курьеров</span>
      <input
        v-model="searchQuery"
        class="input"
        type="search"
        placeholder="Имя, email или телефон"
        autocomplete="off"
        data-od-id="courier-search"
      />
    </label>
    <label>
      <span class="visually-hidden">Город</span>
      <select v-model="cityFilter" class="select" data-od-id="city-filter">
        <option value="all">Все города</option>
        <option value="Вена">Вена</option>
        <option value="Грац">Грац</option>
        <option value="Линц">Линц</option>
        <option value="Зальцбург">Зальцбург</option>
      </select>
    </label>
    <label>
      <span class="visually-hidden">Статус платформы</span>
      <select v-model="statusFilter" class="select" data-od-id="status-filter">
        <option value="all">Любой статус</option>
        <option value="active">Активен</option>
        <option value="review">На проверке</option>
        <option value="blocked">Заблокирован</option>
      </select>
    </label>
    <div class="toolbar-note" aria-live="polite">{{ summary }}</div>
  </div>
</template>
