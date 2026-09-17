<script setup lang="ts">
import { nextTick, ref } from 'vue'
import type { TransportPaymentType, TransportRental } from '../../types/transport'
import AppModal from '../ui/AppModal.vue'
import { isTransportPaymentType, transportPaymentLabels } from './transportPayment'

const props = defineProps<{ rental: TransportRental; saving: boolean; error: string }>()
const emit = defineEmits<{ close: []; save: [paymentType: TransportPaymentType] }>()
const paymentType = ref(props.rental.paymentType ?? '')
const fieldError = ref('')

function submit() {
  fieldError.value = ''
  if (!isTransportPaymentType(paymentType.value)) {
    fieldError.value = 'Выберите тип оплаты.'
    void nextTick(() => document.getElementById('rental-edit-paymentType')?.focus())
    return
  }
  emit('save', paymentType.value)
}
</script>

<template>
  <AppModal label-id="rentalPaymentTitle" modal-class="modal-confirm" data-od-id="rental-payment-dialog" @close="$emit('close')">
    <div class="modal-header"><div class="row-between"><h2 id="rentalPaymentTitle">Тип оплаты аренды</h2><button class="btn btn-ghost btn-icon" type="button" aria-label="Закрыть" :disabled="saving" @click="$emit('close')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg></button></div></div>
    <form novalidate @submit.prevent="submit">
      <div class="modal-body">
        <div class="field" :class="{ invalid: fieldError }">
          <label class="required" for="rental-edit-paymentType">Тип оплаты</label>
          <select id="rental-edit-paymentType" v-model="paymentType" class="select" :disabled="saving" :aria-invalid="Boolean(fieldError)" aria-describedby="rental-edit-paymentType-hint rental-edit-paymentType-error">
            <option disabled value="">Выберите тип оплаты</option>
            <option v-for="(label, value) in transportPaymentLabels" :key="value" :value="value">{{ label }}</option>
          </select>
          <span id="rental-edit-paymentType-hint" class="admin-state-note">«Неделя назад» — оплата за прошедшую неделю.</span>
          <span id="rental-edit-paymentType-error" class="field-error">{{ fieldError }}</span>
        </div>
        <p v-if="error" class="form-api-error" role="alert">{{ error }}</p>
      </div>
      <div class="modal-footer"><button class="btn btn-secondary" type="button" :disabled="saving" @click="$emit('close')">Отмена</button><button class="btn btn-primary" type="submit" :disabled="saving">{{ saving ? 'Сохраняем…' : 'Сохранить' }}</button></div>
    </form>
  </AppModal>
</template>
