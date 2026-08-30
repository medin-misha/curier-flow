<script setup lang="ts">
import type { Admin } from '../../types/admin'
import AppModal from '../ui/AppModal.vue'

defineProps<{
  admin: Admin
  saving: boolean
  error: string
}>()

defineEmits<{
  close: []
  confirm: []
}>()
</script>

<template>
  <AppModal label-id="deactivateAdminTitle" modal-class="modal-confirm" data-od-id="deactivate-admin-dialog" @close="$emit('close')">
    <div class="modal-header">
      <div class="row-between">
        <div>
          <p class="eyebrow">Ограничение доступа</p>
          <h2 id="deactivateAdminTitle">Деактивировать администратора?</h2>
        </div>
        <button class="btn btn-ghost btn-icon" type="button" aria-label="Закрыть" :disabled="saving" @click="$emit('close')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
            <path d="m6 6 12 12M18 6 6 18" />
          </svg>
        </button>
      </div>
    </div>
    <div class="modal-body">
      <p>Учётная запись <strong>{{ admin.username }}</strong> потеряет доступ к панели, а её refresh-сессии будут отозваны. Запись останется в реестре и её можно будет активировать повторно.</p>
      <p v-if="error" class="form-api-error" role="alert">{{ error }}</p>
    </div>
    <div class="modal-footer">
      <button class="btn btn-secondary" type="button" :disabled="saving" @click="$emit('close')">Отмена</button>
      <button class="btn btn-danger" type="button" :disabled="saving" @click="$emit('confirm')">{{ saving ? 'Деактивируем…' : 'Деактивировать' }}</button>
    </div>
  </AppModal>
</template>
