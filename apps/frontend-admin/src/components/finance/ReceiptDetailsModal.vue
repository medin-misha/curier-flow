<script setup lang="ts">
import type { StoredFile } from '../../types/file'
import type { Receipt, ReceiptTag } from '../../types/receipt'
import AppModal from '../ui/AppModal.vue'
import { formatReceiptDate } from './receiptDate'

const props = defineProps<{
  receipt: Receipt
  tags: ReceiptTag[]
  file: StoredFile | null
  fileLoading: boolean
  fileError: string
  busy: boolean
  refreshing: boolean
  downloading: boolean
}>()

defineEmits<{
  close: []
  edit: []
  remove: []
  download: []
  retryFile: []
}>()

function formatDate(value: string) {
  return new Intl.DateTimeFormat('ru-RU', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Europe/Prague',
  }).format(new Date(value))
}

function formatSize(size: number) {
  if (size < 1024) return `${size} Б`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} КБ`
  return `${(size / (1024 * 1024)).toFixed(1)} МБ`
}

function tagName(tagId: string | null) {
  return tagId ? (props.tags.find((tag) => tag.id === tagId)?.name ?? 'Неизвестный тег') : 'Без тега'
}
</script>

<template>
  <AppModal
    label-id="receiptDetailTitle"
    modal-class="modal-detail"
    data-od-id="receipt-detail-dialog"
    @close="$emit('close')"
  >
    <div class="modal-header">
      <div class="row-between">
        <div>
          <p class="eyebrow">Карточка чека</p>
          <h2 id="receiptDetailTitle" class="num">{{ receipt.amount }} Kč</h2>
          <p class="num">ID {{ receipt.id }}</p>
        </div>
        <button class="btn btn-ghost btn-icon" type="button" aria-label="Закрыть" :disabled="busy" @click="$emit('close')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
            <path d="m6 6 12 12M18 6 6 18" />
          </svg>
        </button>
      </div>
    </div>

    <div class="modal-body">
      <div class="detail-grid">
        <div class="detail-item">
          <span>Сумма</span>
          <strong class="num">{{ receipt.amount }} Kč</strong>
        </div>
        <div class="detail-item">
          <span>Файл ID</span>
          <strong class="num">{{ receipt.fileId }}</strong>
        </div>
        <div class="detail-item">
          <span>Дата чека</span>
          <strong class="num">{{ formatReceiptDate(receipt.date) }}</strong>
        </div>
        <div class="detail-item">
          <span>Тип расхода</span>
          <strong><span class="tag">{{ tagName(receipt.tagId) }}</span></strong>
        </div>
        <div class="detail-item">
          <span>Создан</span>
          <strong class="num">{{ formatDate(receipt.createdAt) }}</strong>
        </div>
        <div class="detail-item">
          <span>Обновлён</span>
          <strong class="num">{{ formatDate(receipt.updatedAt) }}</strong>
        </div>
      </div>

      <div class="detail-group">
        <div class="row-between">
          <div>
            <h3>Файл чека</h3>
            <p class="admin-state-note">Файл загружается только при открытии карточки.</p>
          </div>
          <button
            v-if="fileError"
            class="btn btn-secondary btn-compact"
            type="button"
            :disabled="fileLoading"
            @click="$emit('retryFile')"
          >
            Повторить
          </button>
        </div>
        <div v-if="fileLoading" class="receipt-file-state" aria-busy="true">
          <span class="spinner" aria-hidden="true"></span>
          <span>Получаем метаданные…</span>
        </div>
        <p v-else-if="fileError" class="form-api-error" role="alert">{{ fileError }}</p>
        <div v-else-if="file" class="receipt-file-card">
          <div>
            <strong>{{ file.originalName }}</strong>
            <span>{{ file.contentType }} · {{ formatSize(file.size) }}</span>
          </div>
          <span class="status status-ok">{{ file.status === 'ready' ? 'Готов' : file.status }}</span>
        </div>
      </div>
    </div>

    <div class="modal-footer admin-detail-footer">
      <button class="btn btn-danger btn-danger-ghost" type="button" :disabled="busy || refreshing" @click="$emit('remove')">
        Удалить
      </button>
      <span class="modal-footer-spacer"></span>
      <button
        class="btn btn-secondary"
        type="button"
        :disabled="busy || downloading || !file?.downloadUrl"
        @click="$emit('download')"
      >
        {{ downloading ? 'Готовим…' : 'Скачать' }}
      </button>
      <button class="btn btn-primary" type="button" :disabled="busy || refreshing" @click="$emit('edit')">
        {{ refreshing ? 'Обновляем…' : 'Редактировать' }}
      </button>
    </div>
  </AppModal>
</template>
