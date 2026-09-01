<script setup lang="ts">
import { ref, watch } from 'vue'
import type {
  Courier,
  CourierDocument,
  CourierFile,
  CourierFormValues,
  CourierPlatform,
  PlatformStatus,
} from '../../types/courier'
import AppModal from '../ui/AppModal.vue'

const props = defineProps<{
  courier: Courier
  downloadingFileIds: string[]
  updatingPlatformIds: string[]
  previewUrls: Record<string, string>
  previewLoadingFileIds: string[]
  previewErrorFileIds: string[]
}>()

const emit = defineEmits<{
  close: []
  edit: [field?: keyof CourierFormValues]
  delete: []
  copied: [label: string]
  copyError: [label: string]
  download: [file: CourierFile]
  updatePlatform: [platform: CourierPlatform, status: PlatformStatus]
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

const platformStatusDrafts = ref<Record<string, PlatformStatus>>({})

watch(
  () => props.courier.platforms,
  (platforms) => {
    platformStatusDrafts.value = Object.fromEntries(
      platforms.map((platform) => [
        platform.id,
        platformStatusDrafts.value[platform.id] ?? platform.status,
      ]),
    )
  },
  { immediate: true },
)

function isUpdatingPlatform(platformId: string) {
  return props.updatingPlatformIds.includes(platformId)
}

function hasPlatformStatusChange(platform: CourierPlatform) {
  return platformStatusDrafts.value[platform.id] !== platform.status
}

function submitPlatformStatus(platform: CourierPlatform) {
  const status = platformStatusDrafts.value[platform.id]
  if (status) emit('updatePlatform', platform, status)
}

function formatBirthDate(value: string) {
  if (!value) return 'Не указана'
  const [year, month, day] = value.split('-')
  return `${day}.${month}.${year}`
}

async function writeToClipboard(value: string) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value)
    return
  }

  const textarea = document.createElement('textarea')
  const activeElement = document.activeElement as HTMLElement | null
  textarea.value = value
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  document.body.append(textarea)

  let copied = false
  try {
    textarea.select()
    copied = typeof document.execCommand === 'function' && document.execCommand('copy')
  } finally {
    textarea.remove()
    activeElement?.focus()
  }

  if (!copied) throw new Error('Clipboard is unavailable')
}

async function copyField(label: string, value: string) {
  try {
    await writeToClipboard(value)
    emit('copied', label)
  } catch {
    emit('copyError', label)
  }
}

function handleFieldKeydown(event: KeyboardEvent, label: string, value: string) {
  if (event.key !== 'Enter' && event.key !== ' ') return
  event.preventDefault()
  void copyField(label, value)
}

function editField(field: keyof CourierFormValues) {
  emit('edit', field)
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

function isImageDocument(document: CourierDocument) {
  return document.file.contentType.toLowerCase().startsWith('image/')
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
          <h2
            id="detailTitle"
            class="detail-header-field detail-item-interactive"
            role="button"
            tabindex="0"
            title="Нажмите для копирования, дважды нажмите для редактирования"
            data-copy-field="fullName"
            @click="copyField('Полное имя', courier.fullName)"
            @dblclick="editField('fullName')"
            @keydown="handleFieldKeydown($event, 'Полное имя', courier.fullName)"
          >
            {{ courier.fullName }}
          </h2>
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
        <div
          class="detail-item detail-item-interactive"
          role="button"
          tabindex="0"
          title="Нажмите для копирования, дважды нажмите для редактирования"
          data-copy-field="email"
          @click="copyField('Email', courier.email)"
          @dblclick="editField('email')"
          @keydown="handleFieldKeydown($event, 'Email', courier.email)"
        >
          <span>Email</span><strong>{{ courier.email }}</strong>
        </div>
        <div
          class="detail-item detail-item-interactive"
          role="button"
          tabindex="0"
          title="Нажмите для копирования, дважды нажмите для редактирования"
          data-copy-field="phone"
          @click="copyField('Телефон', courier.phone)"
          @dblclick="editField('phone')"
          @keydown="handleFieldKeydown($event, 'Телефон', courier.phone)"
        >
          <span>Телефон</span><strong class="num">{{ courier.phone }}</strong>
        </div>
        <div
          class="detail-item detail-item-interactive"
          role="button"
          tabindex="0"
          title="Нажмите для копирования, дважды нажмите для редактирования"
          data-copy-field="birthDate"
          @click="copyField('Дата рождения', formatBirthDate(courier.birthDate))"
          @dblclick="editField('birthDate')"
          @keydown="handleFieldKeydown($event, 'Дата рождения', formatBirthDate(courier.birthDate))"
        >
          <span>Дата рождения</span>
          <strong class="num">{{ formatBirthDate(courier.birthDate) }}</strong>
        </div>
        <div
          class="detail-item detail-item-interactive"
          role="button"
          tabindex="0"
          title="Нажмите для копирования, дважды нажмите для редактирования"
          data-copy-field="city"
          @click="copyField('Город', courier.city || 'Не указан')"
          @dblclick="editField('city')"
          @keydown="handleFieldKeydown($event, 'Город', courier.city || 'Не указан')"
        >
          <span>Город</span><strong>{{ courier.city || 'Не указан' }}</strong>
        </div>
        <div
          class="detail-item detail-item-interactive"
          role="button"
          tabindex="0"
          title="Нажмите для копирования, дважды нажмите для редактирования"
          data-copy-field="citizenship"
          @click="copyField('Гражданство', courier.citizenship || 'Не указано')"
          @dblclick="editField('citizenship')"
          @keydown="handleFieldKeydown($event, 'Гражданство', courier.citizenship || 'Не указано')"
        >
          <span>Гражданство</span><strong>{{ courier.citizenship || 'Не указано' }}</strong>
        </div>
        <div
          class="detail-item detail-item-interactive"
          role="button"
          tabindex="0"
          title="Нажмите для копирования, дважды нажмите для редактирования"
          data-copy-field="bankAccount"
          @click="copyField('Банковский счёт', courier.bank || 'Не указан')"
          @dblclick="editField('bankAccount')"
          @keydown="handleFieldKeydown($event, 'Банковский счёт', courier.bank || 'Не указан')"
        >
          <span>Банковский счёт</span>
          <strong class="num">{{ courier.bank || 'Не указан' }}</strong>
        </div>
        <div
          class="detail-item detail-item-interactive"
          role="button"
          tabindex="0"
          title="Нажмите для копирования, дважды нажмите для редактирования"
          data-copy-field="contact"
          @click="copyField('Канал связи', `${courier.contactPlatform || 'Не указан'} · ${courier.contact || '—'}`)"
          @dblclick="editField('contactPlatform')"
          @keydown="handleFieldKeydown($event, 'Канал связи', `${courier.contactPlatform || 'Не указан'} · ${courier.contact || '—'}`)"
        >
          <span>Канал связи</span>
          <strong>{{ courier.contactPlatform || 'Не указан' }} · {{ courier.contact || '—' }}</strong>
        </div>
        <div
          class="detail-item detail-item-interactive"
          role="button"
          tabindex="0"
          title="Нажмите для копирования, дважды нажмите для редактирования"
          data-copy-field="source"
          @click="copyField('Источник', courier.source || 'Не указан')"
          @dblclick="editField('source')"
          @keydown="handleFieldKeydown($event, 'Источник', courier.source || 'Не указан')"
        >
          <span>Источник</span><strong>{{ courier.source || 'Не указан' }}</strong>
        </div>
        <div
          class="detail-item detail-item-interactive"
          role="button"
          tabindex="0"
          title="Нажмите для копирования, дважды нажмите для редактирования"
          data-copy-field="address"
          @click="copyField('Адрес', courier.address || 'Не указан')"
          @dblclick="editField('address')"
          @keydown="handleFieldKeydown($event, 'Адрес', courier.address || 'Не указан')"
        >
          <span>Адрес</span><strong>{{ courier.address || 'Не указан' }}</strong>
        </div>
        <div
          class="detail-item detail-item-interactive"
          role="button"
          tabindex="0"
          title="Нажмите для копирования, дважды нажмите для редактирования"
          data-copy-field="consent"
          @click="copyField('Согласие', courier.consent ? 'Получено' : 'Не получено')"
          @dblclick="editField('consent')"
          @keydown="handleFieldKeydown($event, 'Согласие', courier.consent ? 'Получено' : 'Не получено')"
        >
          <span>Согласие</span><strong>{{ courier.consent ? 'Получено' : 'Не получено' }}</strong>
        </div>
      </div>

      <div class="detail-group">
        <div class="row-between">
          <h3>Платформы</h3>
          <span class="meta">{{ courier.platforms.length }}</span>
        </div>
        <div class="detail-list">
          <div
            v-for="platform in courier.platforms"
            :key="platform.id"
            class="detail-row platform-row"
          >
            <div>
              <strong>{{ platform.name }}</strong>
              <span>Аккаунт платформы доставки</span>
            </div>
            <div class="platform-status-panel">
              <span
                class="status"
                :class="platform.status === 'active' ? 'status-ok' : 'status-warn'"
              >
                {{ statusLabels[platform.status] }}
              </span>
              <div class="platform-status-editor">
                <label
                  class="visually-hidden"
                  :for="`platform-status-${platform.id}`"
                >
                  Новый статус {{ platform.name }}
                </label>
                <select
                  :id="`platform-status-${platform.id}`"
                  v-model="platformStatusDrafts[platform.id]"
                  class="select platform-status-select"
                  :data-od-id="`platform-status-${platform.id}`"
                  :disabled="isUpdatingPlatform(platform.id)"
                >
                  <option value="pending">Ожидает</option>
                  <option value="active">Активен</option>
                  <option value="inactive">Неактивен</option>
                </select>
                <button
                  class="btn btn-secondary platform-status-button"
                  type="button"
                  :disabled="
                    !hasPlatformStatusChange(platform) || isUpdatingPlatform(platform.id)
                  "
                  @click="submitPlatformStatus(platform)"
                >
                  {{ isUpdatingPlatform(platform.id) ? 'Сохранение…' : 'Изменить' }}
                </button>
              </div>
            </div>
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
              <img
                v-if="isImageDocument(document) && previewUrls[document.file.id]"
                :src="previewUrls[document.file.id]"
                :alt="`Миниатюра файла ${document.file.originalName}`"
              />
              <div
                v-else-if="isImageDocument(document) && previewLoadingFileIds.includes(document.file.id)"
                class="document-preview-state"
                role="status"
                aria-live="polite"
              >
                <span class="spinner" aria-hidden="true"></span>
                <span>Загружаем фото…</span>
              </div>
              <div
                v-else-if="isImageDocument(document) && previewErrorFileIds.includes(document.file.id)"
                class="document-preview-state"
                role="img"
                :aria-label="`Превью файла ${document.file.originalName} недоступно`"
              >
                <span class="preview-file-type">{{ fileFormat(document) }}</span>
                <span>Превью недоступно</span>
              </div>
              <div
                v-else
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
