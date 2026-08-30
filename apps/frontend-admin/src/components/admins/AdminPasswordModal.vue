<script setup lang="ts">
import { nextTick, ref } from 'vue'
import type { Admin } from '../../types/admin'
import AppModal from '../ui/AppModal.vue'

defineProps<{
  admin: Admin
  saving: boolean
  error: string
}>()

const emit = defineEmits<{
  close: []
  save: [password: string]
}>()

const password = ref('')
const confirmation = ref('')
const passwordError = ref('')
const confirmationError = ref('')

function submit() {
  passwordError.value =
    password.value.length >= 12 && password.value.length <= 128
      ? ''
      : 'Пароль должен содержать от 12 до 128 символов.'
  confirmationError.value = password.value === confirmation.value ? '' : 'Пароли не совпадают.'
  const firstError = passwordError.value ? 'reset-admin-password' : confirmationError.value ? 'reset-admin-password-confirmation' : ''
  if (firstError) {
    void nextTick(() => document.getElementById(firstError)?.focus())
    return
  }
  emit('save', password.value)
}
</script>

<template>
  <AppModal label-id="resetAdminPasswordTitle" modal-class="modal-confirm" data-od-id="reset-admin-password-dialog" @close="$emit('close')">
    <div class="modal-header">
      <div class="row-between">
        <div>
          <h2 id="resetAdminPasswordTitle">Новый пароль</h2>
          <p>{{ admin.username }}</p>
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
        <div class="form-grid form-grid-single">
          <div class="field" :class="{ invalid: passwordError }">
            <label class="required" for="reset-admin-password">Новый пароль</label>
            <input id="reset-admin-password" v-model="password" class="input" type="password" autocomplete="new-password" :aria-invalid="Boolean(passwordError)" />
            <span class="field-error" role="alert">{{ passwordError }}</span>
          </div>
          <div class="field" :class="{ invalid: confirmationError }">
            <label class="required" for="reset-admin-password-confirmation">Повторите пароль</label>
            <input id="reset-admin-password-confirmation" v-model="confirmation" class="input" type="password" autocomplete="new-password" :aria-invalid="Boolean(confirmationError)" />
            <span class="field-error" role="alert">{{ confirmationError }}</span>
          </div>
        </div>
        <p>Все текущие сессии этого администратора будут завершены.</p>
        <p v-if="error" class="form-api-error" role="alert">{{ error }}</p>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" type="button" :disabled="saving" @click="$emit('close')">Отмена</button>
        <button class="btn btn-primary" type="submit" :disabled="saving">{{ saving ? 'Сохраняем…' : 'Сменить пароль' }}</button>
      </div>
    </form>
  </AppModal>
</template>
