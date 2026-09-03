<script setup lang="ts">
import { computed } from 'vue'
import type { Receipt, ReceiptTag } from '../../types/receipt'
import { formatReceiptDate } from './receiptDate'

const props = defineProps<{
  receipts: Receipt[]
  tags: ReceiptTag[]
}>()

defineEmits<{
  select: [receipt: Receipt, event: MouseEvent]
}>()

function formatDate(value: string) {
  return new Intl.DateTimeFormat('ru-RU', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Europe/Prague',
  }).format(new Date(value))
}

const tagNames = computed(() => new Map(props.tags.map((tag) => [tag.id, tag.name])))

function tagName(tagId: string | null) {
  return tagId ? (tagNames.value.get(tagId) ?? 'Неизвестный тег') : 'Без тега'
}
</script>

<template>
  <div class="table-shell">
    <table v-if="receipts.length" class="ds-table receipts-table" data-od-id="receipts-table">
      <thead>
        <tr>
          <th>Чек</th>
          <th>Сумма</th>
          <th>Дата чека</th>
          <th>Тип расхода</th>
          <th>Создан</th>
          <th>Обновлён</th>
          <th><span class="visually-hidden">Действия</span></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="receipt in receipts" :key="receipt.id" :data-od-id="`receipt-row-${receipt.id}`">
          <td data-label="Чек">
            <div class="person">
              <strong>Файл чека</strong>
              <span class="num">ID {{ receipt.id }}</span>
            </div>
          </td>
          <td data-label="Сумма"><strong class="num">{{ receipt.amount }} Kč</strong></td>
          <td data-label="Дата чека"><span class="num">{{ formatReceiptDate(receipt.date) }}</span></td>
          <td data-label="Тип расхода"><span class="tag">{{ tagName(receipt.tagId) }}</span></td>
          <td data-label="Создан"><span class="num">{{ formatDate(receipt.createdAt) }}</span></td>
          <td data-label="Обновлён"><span class="num">{{ formatDate(receipt.updatedAt) }}</span></td>
          <td data-label="Действия">
            <button
              class="table-action"
              type="button"
              :aria-label="`Открыть чек на сумму ${receipt.amount} Kč`"
              :data-od-id="`open-receipt-${receipt.id}`"
              @click="$emit('select', receipt, $event)"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                <circle cx="12" cy="5" r="1" />
                <circle cx="12" cy="12" r="1" />
                <circle cx="12" cy="19" r="1" />
              </svg>
            </button>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-else class="empty-state">
      <h2>Чеков пока нет</h2>
      <p>Добавьте первый чек, чтобы начать учёт расходов.</p>
    </div>
  </div>
</template>
