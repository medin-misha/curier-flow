<script setup lang="ts">
import type { Courier } from '../../types/courier'
import AppModal from '../ui/AppModal.vue'

defineProps<{
  courier: Courier
  deleting: boolean
  error: string
}>()

defineEmits<{
  close: []
  confirm: []
}>()
</script>

<template>
  <AppModal
    label-id="deleteTitle"
    modal-class="modal-confirm"
    data-od-id="delete-courier-dialog"
    @close="$emit('close')"
  >
    <div class="modal-header">
      <div class="row-between">
        <div>
          <p class="eyebrow">Необратимое действие</p>
          <h2 id="deleteTitle">Удалить курьера?</h2>
        </div>
        <button
          class="btn btn-ghost btn-icon"
          type="button"
          aria-label="Закрыть"
          :disabled="deleting"
          @click="$emit('close')"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
            <path d="m6 6 12 12M18 6 6 18" />
          </svg>
        </button>
      </div>
    </div>
    <div class="modal-body">
      <p>
        Профиль <strong>{{ courier.fullName }}</strong>, платформы и связанные документы
        будут удалены.
      </p>
      <p v-if="error" class="form-api-error" role="alert">{{ error }}</p>
    </div>
    <div class="modal-footer">
      <button class="btn btn-secondary" type="button" :disabled="deleting" @click="$emit('close')">
        Отмена
      </button>
      <button class="btn btn-danger" type="button" :disabled="deleting" @click="$emit('confirm')">
        {{ deleting ? 'Удаляем…' : 'Удалить' }}
      </button>
    </div>
  </AppModal>
</template>
