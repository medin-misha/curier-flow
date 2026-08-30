<script setup lang="ts">
import type { DocumentTemplate } from '../../types/document'
import AppModal from '../ui/AppModal.vue'

defineProps<{
  template: DocumentTemplate
  busy: boolean
  refreshing: boolean
}>()

defineEmits<{
  close: []
  render: []
  remove: []
}>()

function formatDate(value: string) {
  return new Intl.DateTimeFormat('ru-RU', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Europe/Prague',
  }).format(new Date(value))
}

function placeholder(group: string | number, field: string) {
  return `{${String(group)}.${field}}`
}
</script>

<template>
  <AppModal
    label-id="documentTemplateDetailTitle"
    modal-class="modal-detail"
    data-od-id="document-template-detail-dialog"
    @close="$emit('close')"
  >
    <div class="modal-header">
      <div class="row-between">
        <div>
          <p class="eyebrow">Карточка шаблона</p>
          <h2 id="documentTemplateDetailTitle">{{ template.name }}</h2>
          <p class="num">ID {{ template.id }}</p>
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
          <span>Исходный File ID</span>
          <strong class="num">{{ template.fileId }}</strong>
        </div>
        <div class="detail-item">
          <span>Групп полей</span>
          <strong>{{ Object.keys(template.fields).length }}</strong>
        </div>
        <div class="detail-item">
          <span>Создан</span>
          <strong class="num">{{ formatDate(template.createdAt) }}</strong>
        </div>
        <div class="detail-item">
          <span>Обновлён</span>
          <strong class="num">{{ formatDate(template.updatedAt) }}</strong>
        </div>
      </div>

      <div class="detail-group">
        <div class="row-between">
          <div>
            <h3>Схема значений</h3>
            <p class="admin-state-note">При генерации нужно передать точный набор этих полей.</p>
          </div>
          <span v-if="refreshing" class="meta">Обновляем…</span>
        </div>
        <div class="template-field-groups">
          <section v-for="(fields, group) in template.fields" :key="group" class="template-field-group">
            <strong>{{ group }}</strong>
            <div class="tag-list">
              <code v-for="field in fields" :key="field" class="tag">{{ placeholder(group, field) }}</code>
            </div>
          </section>
        </div>
      </div>
    </div>

    <div class="modal-footer admin-detail-footer">
      <button class="btn btn-danger btn-danger-ghost" type="button" :disabled="busy || refreshing" @click="$emit('remove')">
        Удалить
      </button>
      <span class="modal-footer-spacer"></span>
      <button class="btn btn-secondary" type="button" :disabled="busy" @click="$emit('close')">Закрыть</button>
      <button class="btn btn-primary" type="button" :disabled="busy || refreshing" data-od-id="render-document" @click="$emit('render')">
        Сформировать документ
      </button>
    </div>
  </AppModal>
</template>
