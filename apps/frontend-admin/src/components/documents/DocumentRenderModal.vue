<script setup lang="ts">
import { reactive } from 'vue'
import type { DocumentRenderValues, DocumentTemplate } from '../../types/document'
import AppModal from '../ui/AppModal.vue'

const props = defineProps<{
  template: DocumentTemplate
  rendering: boolean
  error: string
}>()

const emit = defineEmits<{
  close: []
  render: [values: DocumentRenderValues]
}>()

const values = reactive<DocumentRenderValues>(
  Object.fromEntries(
    Object.entries(props.template.fields).map(([group, fields]) => [
      group,
      Object.fromEntries(fields.map((field) => [field, ''])),
    ]),
  ),
)

function fieldId(group: string, field: string) {
  return `document-value-${group}-${field}`.replace(/[^a-zA-Z0-9_-]/g, '-')
}

function updateValue(group: string, field: string, event: Event) {
  const groupValues = values[group]
  if (groupValues) groupValues[field] = (event.currentTarget as HTMLInputElement).value
}

function submit() {
  emit(
    'render',
    Object.fromEntries(
      Object.entries(values).map(([group, fields]) => [group, { ...fields }]),
    ),
  )
}
</script>

<template>
  <AppModal
    label-id="documentRenderTitle"
    modal-class="modal-detail"
    data-od-id="document-render-dialog"
    @close="$emit('close')"
  >
    <div class="modal-header">
      <div class="row-between">
        <div>
          <p class="eyebrow">Генерация DOCX</p>
          <h2 id="documentRenderTitle">{{ template.name }}</h2>
          <p>Заполните значения, которые будут подставлены вместо placeholders.</p>
        </div>
        <button class="btn btn-ghost btn-icon" type="button" aria-label="Закрыть" :disabled="rendering" @click="$emit('close')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
            <path d="m6 6 12 12M18 6 6 18" />
          </svg>
        </button>
      </div>
    </div>

    <form @submit.prevent="submit">
      <div class="modal-body">
        <section v-for="(fields, group) in template.fields" :key="group" class="render-field-group">
          <div class="form-section-title">
            <h3>{{ group }}</h3>
            <p>Группа {{ group }} · {{ fields.length }} полей</p>
          </div>
          <div class="form-grid">
            <div v-for="field in fields" :key="field" class="field">
              <label :for="fieldId(String(group), field)">{{ field }}</label>
              <input
                :id="fieldId(String(group), field)"
                class="input"
                type="text"
                maxlength="10000"
                :value="values[String(group)]?.[field]"
                :disabled="rendering"
                :placeholder="`{${String(group)}.${field}}`"
                @input="updateValue(String(group), field, $event)"
              />
              <span class="render-field-path num">{{ group }}.{{ field }}</span>
            </div>
          </div>
        </section>
        <p v-if="error" class="form-api-error" role="alert">{{ error }}</p>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" type="button" :disabled="rendering" @click="$emit('close')">
          Назад
        </button>
        <button class="btn btn-primary" type="submit" data-od-id="download-rendered-document" :disabled="rendering">
          {{ rendering ? 'Формируем…' : 'Сформировать и скачать' }}
        </button>
      </div>
    </form>
  </AppModal>
</template>
