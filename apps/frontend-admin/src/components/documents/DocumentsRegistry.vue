<script setup lang="ts">
import type { DocumentTemplate } from '../../types/document'
import AdminPagination from '../admins/AdminPagination.vue'

defineProps<{
  templates: DocumentTemplate[]
  currentPage: number
  paginationSummary: string
  hasNext: boolean
  loading: boolean
  error: string
}>()

defineEmits<{
  create: [event: MouseEvent]
  select: [template: DocumentTemplate, event: MouseEvent]
  page: [page: number]
  retry: []
}>()

function formatDate(value: string) {
  return new Intl.DateTimeFormat('ru-RU', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Europe/Prague',
  }).format(new Date(value))
}

function fieldCount(template: DocumentTemplate) {
  return Object.values(template.fields).reduce((total, fields) => total + fields.length, 0)
}
</script>

<template>
  <section class="section" data-od-id="documents-registry">
    <div class="container">
      <div class="row-between page-heading">
        <div>
          <p class="eyebrow">Documents API</p>
          <h1 data-od-id="documents-title">Шаблоны документов</h1>
        </div>
        <button class="btn btn-primary" type="button" data-od-id="create-document-template" @click="$emit('create', $event)">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
            <path d="M12 5v14M5 12h14" />
          </svg>
          Добавить шаблон
        </button>
      </div>

      <div class="documents-guide" aria-label="Формат шаблонов">
        <div>
          <span>Синтаксис поля</span>
          <strong class="num">{courier.full_name}</strong>
        </div>
        <p>Группы courier, transport и transport_courier заполняются из реестров. Остальные поля доступны для ручного ввода; готовые документы не сохраняются.</p>
      </div>

      <div class="card" data-od-id="document-templates-table-card">
        <div v-if="loading && !templates.length" class="registry-state" aria-busy="true">
          <span class="spinner" aria-hidden="true"></span>
          <h2>Загружаем шаблоны</h2>
          <p>Получаем реестр из Documents API.</p>
        </div>
        <div v-else-if="error" class="registry-state registry-error" role="alert">
          <h2>Не удалось загрузить реестр</h2>
          <p>{{ error }}</p>
          <button class="btn btn-secondary" type="button" @click="$emit('retry')">Повторить</button>
        </div>
        <template v-else>
          <div class="table-shell">
            <table v-if="templates.length" class="ds-table templates-table" data-od-id="document-templates-table">
              <thead>
                <tr>
                  <th>Шаблон</th>
                  <th>Схема</th>
                  <th>Создан</th>
                  <th>Обновлён</th>
                  <th><span class="visually-hidden">Действия</span></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="template in templates" :key="template.id" :data-od-id="`document-template-row-${template.id}`">
                  <td data-label="Шаблон">
                    <div class="person">
                      <strong>{{ template.name }}</strong>
                      <span class="num">ID {{ template.id }}</span>
                    </div>
                  </td>
                  <td data-label="Схема">
                    <strong>{{ fieldCount(template) }} полей</strong>
                    <span class="template-groups">{{ Object.keys(template.fields).join(', ') }}</span>
                  </td>
                  <td data-label="Создан"><span class="num">{{ formatDate(template.createdAt) }}</span></td>
                  <td data-label="Обновлён"><span class="num">{{ formatDate(template.updatedAt) }}</span></td>
                  <td data-label="Действия">
                    <button
                      class="table-action"
                      type="button"
                      :aria-label="`Открыть шаблон ${template.name}`"
                      :data-od-id="`open-document-template-${template.id}`"
                      @click="$emit('select', template, $event)"
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
              <h2>Шаблонов пока нет</h2>
              <p>Добавьте DOCX с полями, чтобы генерировать документы.</p>
            </div>
          </div>
          <AdminPagination
            :current-page="currentPage"
            :summary="paginationSummary"
            :can-next="hasNext"
            :loading="loading"
            entity-label="шаблонов"
            data-od-id="document-templates-pagination"
            @page="$emit('page', $event)"
          />
        </template>
      </div>
    </div>
  </section>
</template>
