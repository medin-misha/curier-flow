<script setup lang="ts">
defineProps<{
  summary: string
  loading: boolean
}>()

const emit = defineEmits<{
  search: []
}>()

const searchQuery = defineModel<string>('searchQuery', { required: true })

function clear() {
  searchQuery.value = ''
  emit('search')
}
</script>

<template>
  <form class="toolbar toolbar-api" data-od-id="couriers-filters" @submit.prevent="$emit('search')">
    <label class="control-wrap">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
        <circle cx="11" cy="11" r="6.5" />
        <path d="m16 16 4 4" />
      </svg>
      <span class="visually-hidden">Точный поиск курьеров</span>
      <input
        v-model="searchQuery"
        class="input"
        type="search"
        placeholder="Точное имя, email или телефон"
        autocomplete="off"
        data-od-id="courier-search"
      />
    </label>
    <button class="btn btn-secondary" type="submit" :disabled="loading">Найти</button>
    <button
      class="btn btn-ghost"
      type="button"
      :disabled="loading || !searchQuery"
      @click="clear"
    >
      Сбросить
    </button>
    <div class="toolbar-note" aria-live="polite">{{ summary }}</div>
  </form>
</template>
