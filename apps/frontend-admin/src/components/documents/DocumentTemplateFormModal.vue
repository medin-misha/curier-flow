<script setup lang="ts">
import { nextTick, ref } from 'vue'
import type { DocumentTemplateFormInput } from '../../types/document'
import AppModal from '../ui/AppModal.vue'
import {
  normalizeTemplateName,
  validateTemplateFile,
  validateTemplateName,
} from './documentForm'

defineProps<{
  saving: boolean
  error: string
}>()

const emit = defineEmits<{
  close: []
  save: [input: DocumentTemplateFormInput]
}>()

const name = ref('')
const file = ref<File | null>(null)
const nameError = ref('')
const fileError = ref('')

function selectFile(event: Event) {
  const input = event.currentTarget as HTMLInputElement
  const selected = input.files?.[0] ?? null
  const error = validateTemplateFile(selected)
  fileError.value = error
  if (error) {
    input.value = ''
    file.value = null
    return
  }
  file.value = selected
}

function submit() {
  nameError.value = validateTemplateName(name.value)
  fileError.value = validateTemplateFile(file.value)
  if (nameError.value || fileError.value || !file.value) {
    const target = nameError.value ? 'document-template-name' : 'document-template-file'
    void nextTick(() => document.getElementById(target)?.focus())
    return
  }
  emit('save', { name: normalizeTemplateName(name.value), file: file.value })
}
</script>

<template>
  <AppModal
    label-id="documentTemplateFormTitle"
    data-od-id="document-template-form-dialog"
    @close="$emit('close')"
  >
    <div class="modal-header">
      <div class="row-between">
        <div>
          <p class="eyebrow">Documents</p>
          <h2 id="documentTemplateFormTitle">Новый шаблон</h2>
          <p>Загрузите DOCX с полями, например {courier.full_name}.</p>
        </div>
        <button
          class="btn btn-ghost btn-icon"
          type="button"
          aria-label="Закрыть"
          :disabled="saving"
          @click="$emit('close')"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
            <path d="m6 6 12 12M18 6 6 18" />
          </svg>
        </button>
      </div>
    </div>

    <form novalidate @submit.prevent="submit">
      <div class="modal-body">
        <div class="form-section">
          <div class="form-section-title">
            <h3>Описание шаблона</h3>
            <p>Название попадёт в имя сгенерированного документа.</p>
          </div>
          <div class="form-grid form-grid-single">
            <div class="field" :class="{ invalid: nameError }">
              <label class="required" for="document-template-name">Название</label>
              <input
                id="document-template-name"
                v-model="name"
                class="input"
                maxlength="255"
                placeholder="Договор аренды велосипеда"
                :aria-invalid="Boolean(nameError)"
                aria-describedby="document-template-name-error"
                :disabled="saving"
              />
              <span id="document-template-name-error" class="field-error" role="alert">{{ nameError }}</span>
            </div>
          </div>
        </div>

        <div class="form-section">
          <div class="form-section-title">
            <h3>Исходный файл</h3>
            <p>Формат поля: {courier.full_name}. Только строчные латинские буквы, цифры и _; обе части начинаются с буквы.</p>
          </div>
          <div class="file-control" :class="{ invalid: fileError }">
            <div class="file-copy">
              <strong>{{ file?.name || 'Выберите шаблон' }}</strong>
              <span>DOCX · до 25 МБ · макросы не поддерживаются</span>
              <span id="document-template-file-error" class="file-error" role="alert">{{ fileError }}</span>
            </div>
            <input
              id="document-template-file"
              type="file"
              aria-label="DOCX-файл шаблона"
              :aria-invalid="Boolean(fileError)"
              aria-describedby="document-template-file-error"
              accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              :disabled="saving"
              @change="selectFile"
            />
          </div>
        </div>
        <p v-if="error" class="form-api-error" role="alert">{{ error }}</p>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" type="button" :disabled="saving" @click="$emit('close')">
          Отмена
        </button>
        <button class="btn btn-primary" type="submit" data-od-id="save-document-template" :disabled="saving">
          {{ saving ? 'Проверяем DOCX…' : 'Создать шаблон' }}
        </button>
      </div>
    </form>
  </AppModal>
</template>
