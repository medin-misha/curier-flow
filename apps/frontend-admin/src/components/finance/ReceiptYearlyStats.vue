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

function formatMonth(month: number) {
  const name = new Intl.DateTimeFormat('ru-RU', {
    month: 'long',
    timeZone: 'UTC',
  }).format(new Date(Date.UTC(2024, month - 1, 1)))
  return name.charAt(0).toUpperCase() + name.slice(1)
}

function receiptCount(count: number) {
  const lastTwoDigits = count % 100
  const lastDigit = count % 10
  if (lastTwoDigits >= 11 && lastTwoDigits <= 14) return `${count} чеков`
  if (lastDigit === 1) return `${count} чек`
  if (lastDigit >= 2 && lastDigit <= 4) return `${count} чека`
  return `${count} чеков`
}
</script>

<template>
  <section class="finance-stats" aria-labelledby="finance-stats-title" :aria-busy="loading">
    <div class="finance-stats-heading">
      <div>
        <p class="eyebrow">Помесячный обзор</p>
        <h2 id="finance-stats-title">Расходы по месяцам</h2>
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
      <div class="finance-monthly-breakdown" data-od-id="receipt-monthly-stats">
        <div class="row-between finance-breakdown-heading">
          <h3>По месяцам</h3>
          <span>Даты чеков за {{ selected.year }} год</span>
        </div>
        <div v-if="selected.months.length" class="finance-monthly-rows">
          <div
            v-for="monthStat in selected.months"
            :key="monthStat.month"
            class="finance-monthly-row"
            :data-od-id="`receipt-stats-month-${monthStat.month}`"
          >
            <span>{{ formatMonth(monthStat.month) }}</span>
            <span class="num finance-monthly-count">{{ receiptCount(monthStat.count) }}</span>
            <strong class="num">{{ monthStat.amount }} Kč</strong>
          </div>
        </div>
        <p v-else class="finance-monthly-empty">За этот год расходов нет.</p>
      </div>
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
      <div class="finance-tag-breakdown">
        <h3>По типам расходов за год</h3>
        <div class="finance-tag-rows">
          <div v-for="tag in selected.tags" :key="tag.tagId ?? 'untagged'" class="finance-tag-row">
            <span class="tag">{{ tag.name }}</span>
            <span class="num">{{ tag.count }} чеков</span>
            <strong class="num">{{ tag.amount }} Kč</strong>
          </div>
        </div>
      </div>
      <p v-if="error" class="finance-stats-warning" role="alert">
        {{ error }} Показаны ранее загруженные данные.
        <button type="button" @click="$emit('retry')">Повторить</button>
      </p>
      <p v-else-if="loading" class="finance-stats-warning">Обновляем статистику…</p>
    </template>
  </section>
</template>
