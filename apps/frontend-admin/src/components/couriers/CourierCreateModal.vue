<script setup lang="ts">
import { nextTick, reactive, ref } from 'vue'
import type {
  CourierCreateInput,
  CourierFormErrors,
  CourierFormValues,
  DeliveryPlatform,
  DocumentPurpose,
  DocumentType,
} from '../../types/courier'
import AppModal from '../ui/AppModal.vue'
import CourierProfileFields from './CourierProfileFields.vue'

const MAX_FILE_SIZE = 10 * 1024 * 1024
const ALLOWED_FILE_TYPES = new Set(['application/pdf', 'image/jpeg', 'image/png'])

defineProps<{
  saving: boolean
  error: string
}>()

const emit = defineEmits<{
  close: []
  submit: [input: CourierCreateInput]
}>()

const form = reactive<CourierFormValues>({
  fullName: '',
  birthDate: '',
  email: '',
  phone: '',
  city: '',
  citizenship: '',
  address: '',
  bankAccount: '',
  source: '',
  contactPlatform: '',
  contact: '',
  consent: false,
})
const errors = reactive<CourierFormErrors>({
  fullName: false,
  birthDate: false,
  email: false,
  phone: false,
})
const platform = ref<DeliveryPlatform>('wolt')
const selectedFile = ref<File | null>(null)
const documentType = ref<DocumentType>('other')
const documentPurpose = ref<DocumentPurpose>('platform_onboarding')
const fileError = ref('')

function onFileChange(event: Event) {
  const input = event.currentTarget as HTMLInputElement
  const file = input.files?.[0] ?? null
  fileError.value = ''

  if (file && !ALLOWED_FILE_TYPES.has(file.type)) {
    fileError.value = 'Выберите PDF, JPG или PNG.'
    input.value = ''
    selectedFile.value = null
    return
  }
  if (file && file.size > MAX_FILE_SIZE) {
    fileError.value = 'Размер файла не должен превышать 10 МБ.'
    input.value = ''
    selectedFile.value = null
    return
  }
  selectedFile.value = file
}

function validate() {
  errors.fullName = form.fullName.trim() === ''
  errors.birthDate = form.birthDate === ''
  errors.email = !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())
  errors.phone = form.phone.trim() === ''
  const firstError = (Object.keys(errors) as Array<keyof CourierFormErrors>).find(
    (field) => errors[field],
  )
  if (firstError) {
    void nextTick(() => document.getElementById(firstError)?.focus())
    return false
  }
  return !fileError.value
}

function submit() {
  if (!validate()) return
  emit('submit', {
    courier: { ...form },
    platform: platform.value,
    document: selectedFile.value
      ? {
          file: selectedFile.value,
          type: documentType.value,
          purpose: documentPurpose.value,
        }
      : undefined,
  })
}
</script>

<template>
  <AppModal label-id="createTitle" data-od-id="create-courier-dialog" @close="$emit('close')">
    <div class="modal-header">
      <div class="row-between">
        <div>
          <h2 id="createTitle">Новый курьер</h2>
          <p>Профиль будет создан через Courier API.</p>
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
            <h3>Основные данные</h3>
            <p>Поля с отметкой обязательны для создания профиля.</p>
          </div>
          <CourierProfileFields :form="form" :errors="errors" />
        </div>

        <div class="form-section">
          <div class="form-section-title">
            <h3>Регистрация на платформе</h3>
            <p>Backend требует хотя бы одну платформу и создаёт её в статусе «Ожидает».</p>
          </div>
          <div class="form-grid">
            <div class="field">
              <label class="required" for="platform">Платформа доставки</label>
              <select id="platform" v-model="platform" class="select">
                <option value="wolt">Wolt</option>
                <option value="foodora">Foodora</option>
                <option value="bolt_food">Bolt Food</option>
              </select>
            </div>
          </div>
        </div>

        <div class="form-section">
          <div class="form-section-title">
            <h3>Первый документ</h3>
            <p>Необязательно. Метаданные и файл отправляются одним multipart-запросом.</p>
          </div>
          <div v-if="selectedFile" class="form-grid document-fields">
            <div class="field">
              <label for="documentType">Тип документа</label>
              <select id="documentType" v-model="documentType" class="select">
                <option value="passport">Паспорт</option>
                <option value="identity_card">Удостоверение личности</option>
                <option value="residence_permit">Вид на жительство</option>
                <option value="work_permit">Разрешение на работу</option>
                <option value="driving_license">Водительское удостоверение</option>
                <option value="other">Другой документ</option>
              </select>
            </div>
            <div class="field">
              <label for="documentPurpose">Цель хранения</label>
              <select id="documentPurpose" v-model="documentPurpose" class="select">
                <option value="platform_onboarding">Регистрация на платформе</option>
                <option value="employment_compliance">Трудовые требования</option>
                <option value="other">Другая цель</option>
              </select>
            </div>
          </div>
          <div class="file-control" :class="{ invalid: fileError }">
            <div class="file-copy">
              <strong>{{ selectedFile?.name || 'Документ курьера' }}</strong>
              <span>PDF, JPG или PNG · до 10 МБ</span>
              <span v-if="fileError" class="file-error" role="alert">{{ fileError }}</span>
            </div>
            <input type="file" accept=".pdf,.jpg,.jpeg,.png" @change="onFileChange" />
          </div>
        </div>
        <p v-if="error" class="form-api-error" role="alert">{{ error }}</p>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" type="button" :disabled="saving" @click="$emit('close')">
          Отмена
        </button>
        <button class="btn btn-primary" type="submit" data-od-id="submit-courier" :disabled="saving">
          {{ saving ? 'Создаём…' : 'Создать курьера' }}
        </button>
      </div>
    </form>
  </AppModal>
</template>
