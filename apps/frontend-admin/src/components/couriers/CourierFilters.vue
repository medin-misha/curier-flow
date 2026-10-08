<script setup lang="ts">
import { computed } from 'vue'
import type { PlatformStatus } from '../../types/courier'

defineProps<{
  summary: string
  disabled: boolean
}>()

const searchQuery = defineModel<string>('searchQuery', { required: true })
const status = defineModel<PlatformStatus | ''>('status', { required: true })

const hasFilters = computed(() => Boolean(searchQuery.value || status.value))

const statusOptions: Array<{ value: PlatformStatus; label: string }> = [
  { value: 'active', label: 'Активен' },
  { value: 'pending', label: 'Ожидает' },
  { value: 'inactive', label: 'Неактивен' },
  { value: 'problem', label: 'Проблема' },
]

function clear() {
  searchQuery.value = ''
  status.value = ''
}
</script>

<template>
  <form class="toolbar toolbar-api" data-od-id="couriers-filters" @submit.prevent>
    <label class="control-wrap">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
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
        maxlength="320"
        :disabled="disabled"
        data-od-id="courier-search"
      />
    </label>
    <select
      v-model="status"
      class="select"
      :disabled="disabled"
      aria-label="Статус курьера"
      data-od-id="courier-status-filter"
    >
      <option value="">Все статусы</option>
      <option v-for="option in statusOptions" :key="option.value" :value="option.value">
        {{ option.label }}
      </option>
    </select>
    <button
      class="btn btn-ghost"
      type="button"
      :disabled="disabled || !hasFilters"
      @click="clear"
    >
      Сбросить
    </button>
    <div class="toolbar-note" aria-live="polite">{{ summary }}</div>
  </form>
</template>
