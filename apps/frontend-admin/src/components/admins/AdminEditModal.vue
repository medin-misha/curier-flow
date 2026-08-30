<script setup lang="ts">
import { nextTick, reactive } from 'vue'
import type { Admin, AdminUpdateInput } from '../../types/admin'
import AppModal from '../ui/AppModal.vue'
import AdminProfileFields from './AdminProfileFields.vue'
import {
  validateAdminProfile,
  type AdminProfileErrors,
  type AdminProfileForm,
} from './adminForm'

const props = defineProps<{
  admin: Admin
  saving: boolean
  error: string
}>()

const emit = defineEmits<{
  close: []
  save: [input: AdminUpdateInput]
}>()

const form = reactive<AdminProfileForm>({
  username: props.admin.username,
  telegramId: props.admin.telegramId?.toString() ?? '',
})
const errors = reactive<AdminProfileErrors>({ username: '', telegramId: '' })

function submit() {
  const result = validateAdminProfile(form)
  Object.assign(errors, result.errors)
  if (!result.input) {
    const firstErrorId = errors.username ? 'edit-admin-username' : 'edit-admin-telegramId'
    void nextTick(() => document.getElementById(firstErrorId)?.focus())
    return
  }
  emit('save', result.input)
}
</script>

<template>
  <AppModal label-id="editAdminTitle" data-od-id="edit-admin-dialog" @close="$emit('close')">
    <div class="modal-header">
      <div class="row-between">
        <div>
          <h2 id="editAdminTitle">Редактирование администратора</h2>
          <p>{{ admin.username }} · ID {{ admin.id }}</p>
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
            <h3>Данные профиля</h3>
            <p>Telegram ID можно очистить, оставив поле пустым.</p>
          </div>
          <AdminProfileFields :form="form" :errors="errors" id-prefix="edit-admin" />
        </div>
        <p v-if="error" class="form-api-error" role="alert">{{ error }}</p>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" type="button" :disabled="saving" @click="$emit('close')">Отмена</button>
        <button class="btn btn-primary" type="submit" :disabled="saving">
          {{ saving ? 'Сохраняем…' : 'Сохранить' }}
        </button>
      </div>
    </form>
  </AppModal>
</template>
