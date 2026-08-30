<script setup lang="ts">
import type { Receipt } from '../../types/receipt'
import AppModal from '../ui/AppModal.vue'

defineProps<{
  receipt: Receipt
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
    label-id="deleteReceiptTitle"
    modal-class="modal-confirm"
    data-od-id="delete-receipt-dialog"
    @close="$emit('close')"
  >
    <div class="modal-header">
      <div class="row-between">
        <div>
          <p class="eyebrow">Необратимое действие</p>
          <h2 id="deleteReceiptTitle">Удалить чек?</h2>
        </div>
        <button class="btn btn-ghost btn-icon" type="button" aria-label="Закрыть" :disabled="deleting" @click="$emit('close')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
            <path d="m6 6 12 12M18 6 6 18" />
          </svg>
        </button>
      </div>
    </div>
    <div class="modal-body">
      <p>Чек на сумму <strong class="num">{{ receipt.amount }} Kč</strong> и связанный файл будут удалены.</p>
      <p v-if="error" class="form-api-error" role="alert">{{ error }}</p>
    </div>
    <div class="modal-footer">
      <button class="btn btn-secondary" type="button" :disabled="deleting" @click="$emit('close')">Отмена</button>
      <button class="btn btn-danger" type="button" :disabled="deleting" @click="$emit('confirm')">
        {{ deleting ? 'Удаляем…' : 'Удалить' }}
      </button>
    </div>
  </AppModal>
</template>
