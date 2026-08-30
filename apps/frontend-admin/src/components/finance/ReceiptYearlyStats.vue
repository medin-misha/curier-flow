<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { ReceiptYearSummary } from '../../types/receipt'

const props = defineProps<{
  stats: ReceiptYearSummary[]
  loading: boolean
  error: string
}>()

defineEmits<{
  retry: []
}>()

const selectedYear = ref<number | null>(null)

watch(
  () => props.stats.map((item) => item.year).join(','),
  () => {
    if (!props.stats.some((item) => item.year === selectedYear.value)) {
      selectedYear.value = props.stats[0]?.year ?? null
    }
  },
  { immediate: true },
)

const selected = computed(() =>
  props.stats.find((item) => item.year === selectedYear.value),
)
</script>

<template>
  <section class="finance-stats" aria-labelledby="finance-stats-title" :aria-busy="loading">
    <div class="finance-stats-heading">
      <div>
        <p class="eyebrow">Годовой обзор</p>
        <h2 id="finance-stats-title">Расходы по чекам</h2>
      </div>
      <label v-if="stats.length" class="finance-year-picker">
        <span>Год</span>
        <select v-model.number="selectedYear" class="select" data-od-id="receipt-stats-year">
          <option v-for="item in stats" :key="item.year" :value="item.year">{{ item.year }}</option>
        </select>
      </label>
    </div>

    <div v-if="loading && !stats.length" class="finance-stats-state">
      <span class="spinner" aria-hidden="true"></span>
      <span>Собираем все страницы чеков…</span>
    </div>
    <div v-else-if="error && !stats.length" class="finance-stats-state" role="alert">
      <span>{{ error }}</span>
      <button class="btn btn-secondary btn-compact" type="button" @click="$emit('retry')">Повторить</button>
    </div>
    <div v-else-if="!selected" class="finance-stats-state">
      <span>Статистика появится после добавления первого чека.</span>
    </div>
    <template v-else>
      <div class="finance-metrics">
        <article class="finance-metric">
          <span>Общая сумма</span>
          <strong class="num" data-od-id="receipt-stats-amount">{{ selected.amount }} Kč</strong>
          <small>за {{ selected.year }} год</small>
        </article>
        <article class="finance-metric">
          <span>Количество чеков</span>
          <strong class="num" data-od-id="receipt-stats-count">{{ selected.count }}</strong>
          <small>учтено в статистике</small>
        </article>
      </div>
      <p v-if="error" class="finance-stats-warning" role="alert">
        {{ error }} Показаны ранее загруженные данные.
        <button type="button" @click="$emit('retry')">Повторить</button>
      </p>
      <p v-else-if="loading" class="finance-stats-warning">Обновляем статистику…</p>
    </template>
  </section>
</template>
