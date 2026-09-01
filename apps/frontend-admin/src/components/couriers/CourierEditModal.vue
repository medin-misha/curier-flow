<script setup lang="ts">
import { nextTick, onMounted, reactive } from 'vue'
import type {
  Courier,
  CourierFormErrors,
  CourierFormValues,
  CourierUpdateInput,
} from '../../types/courier'
import AppModal from '../ui/AppModal.vue'
import CourierProfileFields from './CourierProfileFields.vue'

const props = defineProps<{
  courier: Courier
  saving: boolean
  error: string
  focusField?: keyof CourierFormValues | null
}>()

const emit = defineEmits<{
  close: []
  save: [input: CourierUpdateInput]
}>()

const form = reactive<CourierFormValues>({
  fullName: props.courier.fullName,
  birthDate: props.courier.birthDate,
  email: props.courier.email,
  phone: props.courier.phone,
  city: props.courier.city || '',
  citizenship: props.courier.citizenship || '',
  address: props.courier.address || '',
  bankAccount: props.courier.bank || '',
  source: props.courier.source || '',
  contactPlatform: props.courier.contactPlatform || '',
  contact: props.courier.contact || '',
  consent: props.courier.consent,
})

const errors = reactive<CourierFormErrors>({
  fullName: false,
  birthDate: false,
  email: false,
  phone: false,
})

onMounted(() => {
  if (!props.focusField) return
  void nextTick(() => document.getElementById(`edit-${props.focusField}`)?.focus())
})

function validate() {
  errors.fullName = form.fullName.trim() === ''
  errors.birthDate = form.birthDate === ''
  errors.email = !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())
  errors.phone = form.phone.trim() === ''
  const firstError = (Object.keys(errors) as Array<keyof CourierFormErrors>).find(
    (field) => errors[field],
  )
  if (!firstError) return true
  void nextTick(() => document.getElementById(`edit-${firstError}`)?.focus())
  return false
}

function submit() {
  if (validate()) emit('save', { ...form })
}
</script>

<template>
  <AppModal label-id="editTitle" data-od-id="edit-courier-dialog" @close="$emit('close')">
    <div class="modal-header">
      <div class="row-between">
        <div>
          <h2 id="editTitle">Редактирование курьера</h2>
          <p>{{ courier.fullName }} · ID {{ courier.id }}</p>
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
            <h3>Данные профиля</h3>
            <p>Изменяются scalar-поля, доступные в PATCH-контракте backend.</p>
          </div>
          <CourierProfileFields :form="form" :errors="errors" id-prefix="edit" />
        </div>
        <p v-if="error" class="form-api-error" role="alert">{{ error }}</p>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" type="button" :disabled="saving" @click="$emit('close')">
          Отмена
        </button>
        <button class="btn btn-primary" type="submit" :disabled="saving">
          {{ saving ? 'Сохраняем…' : 'Сохранить' }}
        </button>
      </div>
    </form>
  </AppModal>
</template>
