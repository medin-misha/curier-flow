<script setup lang="ts">
defineProps<{
  currentPage: number
  summary: string
  canNext: boolean
  loading: boolean
}>()

defineEmits<{
  page: [page: number]
}>()
</script>

<template>
  <div class="pagination" data-od-id="couriers-pagination">
    <span class="pagination-summary num">{{ summary }}</span>
    <div class="page-list" aria-label="Текущая страница">
      <span class="page-button active" aria-current="page">{{ currentPage }}</span>
    </div>
    <div class="pagination-actions">
      <button
        class="btn btn-secondary btn-icon"
        type="button"
        aria-label="Предыдущая страница"
        :disabled="loading || currentPage === 1"
        @click="$emit('page', currentPage - 1)"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
          <path d="m15 18-6-6 6-6" />
        </svg>
      </button>
      <button
        class="btn btn-secondary btn-icon"
        type="button"
        aria-label="Следующая страница"
        :disabled="loading || !canNext"
        @click="$emit('page', currentPage + 1)"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
          <path d="m9 6 6 6-6 6" />
        </svg>
      </button>
    </div>
  </div>
</template>
