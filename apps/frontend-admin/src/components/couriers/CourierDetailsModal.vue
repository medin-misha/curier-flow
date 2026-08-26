<script setup lang="ts">
import type {
  Courier,
  CourierDocument,
  CourierFile,
  PlatformStatus,
} from '../../types/courier'
import AppModal from '../ui/AppModal.vue'

defineProps<{
  courier: Courier
  downloadingFileIds: string[]
}>()

defineEmits<{
  close: []
  edit: []
  delete: []
  download: [file: CourierFile]
}>()

const statusLabels: Record<PlatformStatus, string> = {
  active: 'Активен',
  pending: 'Ожидает',
  inactive: 'Неактивен',
}

const documentStatusLabels = {
  ready: 'Готов',
  processing: 'На проверке',
  rejected: 'Нужна замена',
} as const

function formatBirthDate(value: string) {
  if (!value) return 'Не указана'
  const [year, month, day] = value.split('-')
  return `${day}.${month}.${year}`
}

function formatFileSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} КБ`
  return `${(bytes / 1024 / 1024).toLocaleString('ru-RU', {
    maximumFractionDigits: 1,
  })} МБ`
}

function formatDocumentDate(value: string) {
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(new Date(value))
}

function fileFormat(document: CourierDocument) {
  if (document.file.contentType === 'application/pdf') return 'PDF'
  return document.file.contentType.replace('image/', '').toLocaleUpperCase('ru') || 'FILE'
}
</script>

<template>
  <AppModal
    label-id="detailTitle"
    modal-class="modal-detail"
    data-od-id="courier-detail-dialog"
    @close="$emit('close')"
  >
    <div class="modal-header">
      <div class="row-between">
        <div>
          <p class="eyebrow">Профиль курьера</p>
          <h2 id="detailTitle">{{ courier.fullName }}</h2>
          <p class="num">ID {{ courier.id }}</p>
        </div>
        <button
          class="btn btn-ghost btn-icon"
          type="button"
          aria-label="Закрыть"
          @click="$emit('close')"
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            aria-hidden="true"
          >
            <path d="m6 6 12 12M18 6 6 18" />
          </svg>
        </button>
      </div>
    </div>

    <div class="modal-body">
      <div class="detail-grid">
        <div class="detail-item"><span>Email</span><strong>{{ courier.email }}</strong></div>
        <div class="detail-item">
          <span>Телефон</span><strong class="num">{{ courier.phone }}</strong>
        </div>
        <div class="detail-item">
          <span>Дата рождения</span>
          <strong class="num">{{ formatBirthDate(courier.birthDate) }}</strong>
        </div>
        <div class="detail-item">
          <span>Город</span><strong>{{ courier.city || 'Не указан' }}</strong>
        </div>
        <div class="detail-item">
          <span>Гражданство</span><strong>{{ courier.citizenship || 'Не указано' }}</strong>
        </div>
        <div class="detail-item">
          <span>Банковский счёт</span>
          <strong class="num">{{ courier.bank || 'Не указан' }}</strong>
        </div>
        <div class="detail-item">
          <span>Канал связи</span>
          <strong>{{ courier.contactPlatform || 'Не указан' }} · {{ courier.contact || '—' }}</strong>
        </div>
        <div class="detail-item">
          <span>Источник</span><strong>{{ courier.source || 'Не указан' }}</strong>
        </div>
        <div class="detail-item">
          <span>Адрес</span><strong>{{ courier.address || 'Не указан' }}</strong>
        </div>
        <div class="detail-item">
          <span>Согласие</span><strong>{{ courier.consent ? 'Получено' : 'Не получено' }}</strong>
        </div>
      </div>

      <div class="detail-group">
        <div class="row-between">
          <h3>Платформы</h3>
          <span class="meta">{{ courier.platforms.length }}</span>
        </div>
        <div class="detail-list">
          <div v-for="platform in courier.platforms" :key="platform.name" class="detail-row">
            <div>
              <strong>{{ platform.name }}</strong>
              <span>Аккаунт платформы доставки</span>
            </div>
            <span
              class="status"
              :class="platform.status === 'active' ? 'status-ok' : 'status-warn'"
            >
              {{ statusLabels[platform.status] }}
            </span>
          </div>
          <div v-if="!courier.platforms.length" class="detail-row">
            <div>
              <strong>Платформы не подключены</strong>
              <span>Добавьте аккаунт после проверки профиля.</span>
            </div>
          </div>
        </div>
      </div>

      <div class="detail-group">
        <div class="row-between">
          <h3>Документы</h3>
          <span class="meta">{{ courier.documentFiles.length }}</span>
        </div>
        <div v-if="courier.documentFiles.length" class="document-list">
          <article
            v-for="document in courier.documentFiles"
            :key="document.id"
            class="document-card"
            :data-od-id="`document-card-${document.id}`"
          >
            <div class="document-thumb">
              <div
                class="document-preview-page"
                role="img"
                :aria-label="`Миниатюра файла ${document.file.originalName}`"
              >
                <span class="preview-file-type">{{ fileFormat(document) }}</span>
                <span class="preview-header"></span>
                <span class="preview-identity">
                  <span class="preview-photo">
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="1.5"
                      aria-hidden="true"
                    >
                      <circle cx="12" cy="8" r="3" />
                      <path d="M6.5 19c.6-3.1 2.4-5 5.5-5s4.9 1.9 5.5 5" />
                    </svg>
                  </span>
                  <span class="preview-lines">
                    <span class="preview-line"></span>
                    <span class="preview-line preview-line-short"></span>
                    <span class="preview-line"></span>
                  </span>
                </span>
                <span class="preview-lines">
                  <span class="preview-line"></span>
                  <span class="preview-line"></span>
                  <span class="preview-line preview-line-short"></span>
                </span>
                <span class="preview-stamp">MFS</span>
              </div>
            </div>
            <div class="document-info">
              <div class="row-between document-title">
                <div>
                  <strong :title="document.file.originalName">
                    {{ document.file.originalName }}
                  </strong>
                  <p>{{ document.typeLabel }} · {{ document.purposeLabel }}</p>
                </div>
                <span
                  class="status"
                  :class="document.reviewStatus === 'ready' ? 'status-ok' : 'status-warn'"
                >
                  {{ documentStatusLabels[document.reviewStatus] }}
                </span>
              </div>
              <div class="document-meta">
                <div><span>Формат</span><strong>{{ fileFormat(document) }}</strong></div>
                <div>
                  <span>Размер</span>
                  <strong class="num">{{ formatFileSize(document.file.size) }}</strong>
                </div>
                <div>
                  <span>Добавлен</span>
                  <strong class="num">{{ formatDocumentDate(document.createdAt) }}</strong>
                </div>
                <div>
                  <span>Файл</span>
                  <strong>
                    {{ document.file.status === 'ready' ? 'Доступен' : 'Обрабатывается' }}
                  </strong>
                </div>
              </div>
              <div class="document-actions">
                <span class="document-file-id">FILE {{ document.file.id }}</span>
                <button
                  class="btn btn-secondary document-download"
                  type="button"
                  :data-od-id="`download-file-${document.file.id}`"
                  :aria-label="`Скачать файл ${document.file.originalName}`"
                  :title="
                    document.file.status === 'ready'
                      ? `Скачать ${document.file.originalName}`
                      : 'Файл ещё обрабатывается'
                  "
                  :disabled="
                    document.file.status !== 'ready' ||
                    downloadingFileIds.includes(document.file.id)
                  "
                  @click="$emit('download', document.file)"
                >
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.8"
                    aria-hidden="true"
                  >
                    <path d="M12 3v12m0 0 4-4m-4 4-4-4M5 20h14" />
                  </svg>
                  {{
                    downloadingFileIds.includes(document.file.id)
                      ? 'Скачивание…'
                      : 'Скачать'
                  }}
                </button>
              </div>
            </div>
          </article>
        </div>
        <div v-else class="document-empty">
          <strong>Документы ещё не загружены</strong>
          <span>Файлы появятся здесь после добавления в профиль.</span>
        </div>
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-danger btn-danger-ghost" type="button" @click="$emit('delete')">
        Удалить
      </button>
      <span class="modal-footer-spacer"></span>
      <button class="btn btn-secondary" type="button" @click="$emit('close')">
        Закрыть
      </button>
      <button class="btn btn-primary" type="button" @click="$emit('edit')">
        Редактировать
      </button>
    </div>
  </AppModal>
</template>
