<script setup lang="ts">
import { nextTick, reactive, ref } from 'vue'
import type { AdminCreateInput } from '../../types/admin'
import AppModal from '../ui/AppModal.vue'
import AdminProfileFields from './AdminProfileFields.vue'
import {
  validateAdminProfile,
  type AdminProfileErrors,
  type AdminProfileForm,
} from './adminForm'

defineProps<{
  saving: boolean
  error: string
}>()

const emit = defineEmits<{
  close: []
  submit: [input: AdminCreateInput]
}>()

const form = reactive<AdminProfileForm>({ username: '', telegramId: '' })
const errors = reactive<AdminProfileErrors>({ username: '', telegramId: '' })
const password = ref('')
const passwordConfirmation = ref('')
const passwordError = ref('')
const confirmationError = ref('')

function submit() {
  const profile = validateAdminProfile(form)
  Object.assign(errors, profile.errors)
  passwordError.value =
    password.value.length >= 12 && password.value.length <= 128
      ? ''
      : 'Пароль должен содержать от 12 до 128 символов.'
  confirmationError.value =
    password.value === passwordConfirmation.value ? '' : 'Пароли не совпадают.'

  const firstErrorId = errors.username
    ? 'admin-username'
    : errors.telegramId
      ? 'admin-telegramId'
      : passwordError.value
        ? 'admin-password'
        : confirmationError.value
          ? 'admin-password-confirmation'
          : ''
  if (!profile.input || firstErrorId) {
    void nextTick(() => document.getElementById(firstErrorId)?.focus())
    return
  }

  emit('submit', {
    username: profile.input.username,
    telegramId: profile.input.telegramId,
    password: password.value,
  })
}
</script>

<template>
  <AppModal label-id="createAdminTitle" data-od-id="create-admin-dialog" @close="$emit('close')">
    <div class="modal-header">
      <div class="row-between">
        <div>
          <h2 id="createAdminTitle">Новый администратор</h2>
          <p>Учётная запись сразу станет активной.</p>
        </div>
        <button class="btn btn-ghost btn-icon" type="button" aria-label="Закрыть" :disabled="saving" @click="$emit('close')">
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
            <h3>Профиль</h3>
            <p>Username используется для входа и сохраняется в нижнем регистре.</p>
          </div>
          <AdminProfileFields :form="form" :errors="errors" id-prefix="admin" />
        </div>
        <div class="form-section">
          <div class="form-section-title">
            <h3>Пароль</h3>
            <p>От 12 до 128 символов.</p>
          </div>
          <div class="form-grid">
            <div class="field" :class="{ invalid: passwordError }">
              <label class="required" for="admin-password">Пароль</label>
              <input
                id="admin-password"
                v-model="password"
                class="input"
                type="password"
                autocomplete="new-password"
                :aria-invalid="Boolean(passwordError)"
              />
              <span class="field-error" role="alert">{{ passwordError }}</span>
            </div>
            <div class="field" :class="{ invalid: confirmationError }">
              <label class="required" for="admin-password-confirmation">Повторите пароль</label>
              <input
                id="admin-password-confirmation"
                v-model="passwordConfirmation"
                class="input"
                type="password"
                autocomplete="new-password"
                :aria-invalid="Boolean(confirmationError)"
              />
              <span class="field-error" role="alert">{{ confirmationError }}</span>
            </div>
          </div>
        </div>
        <p v-if="error" class="form-api-error" role="alert">{{ error }}</p>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" type="button" :disabled="saving" @click="$emit('close')">Отмена</button>
        <button class="btn btn-primary" type="submit" data-od-id="submit-admin" :disabled="saving">
          {{ saving ? 'Создаём…' : 'Создать администратора' }}
        </button>
      </div>
    </form>
  </AppModal>
</template>
