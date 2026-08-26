<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  currentPage: number
  pageCount: number
  summary: string
  hasResults: boolean
}>()

defineEmits<{
  page: [page: number]
}>()

const pages = computed(() => Array.from({ length: props.pageCount }, (_, index) => index + 1))
</script>

<template>
  <div class="pagination" data-od-id="couriers-pagination">
    <span class="pagination-summary num">{{ summary }}</span>
    <div class="page-list" aria-label="Страницы">
      <button
        v-for="page in pages"
        :key="page"
        class="page-button"
        :class="{ active: page === currentPage }"
        type="button"
        :aria-label="`Страница ${page}`"
        :aria-current="page === currentPage ? 'page' : undefined"
        @click="$emit('page', page)"
      >
        {{ page }}
      </button>
    </div>
    <div class="pagination-actions">
      <button
        class="btn btn-secondary btn-icon"
        type="button"
        aria-label="Предыдущая страница"
        :disabled="currentPage === 1"
        @click="$emit('page', currentPage - 1)"
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.8"
          aria-hidden="true"
        >
          <path d="m15 18-6-6 6-6" />
        </svg>
      </button>
      <button
        class="btn btn-secondary btn-icon"
        type="button"
        aria-label="Следующая страница"
        :disabled="currentPage === pageCount || !hasResults"
        @click="$emit('page', currentPage + 1)"
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.8"
          aria-hidden="true"
        >
          <path d="m9 6 6 6-6 6" />
        </svg>
      </button>
    </div>
  </div>
</template>
