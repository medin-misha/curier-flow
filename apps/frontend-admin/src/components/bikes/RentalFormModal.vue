<script setup lang="ts">
import { nextTick, ref } from 'vue'
import type { TransportRental, TransportRentalInput } from '../../types/transport'
import AppModal from '../ui/AppModal.vue'
import CourierPicker from './CourierPicker.vue'

const props = defineProps<{
  rental?: TransportRental | null
  requireHistorical?: boolean
  saving: boolean
  error: string
}>()
const emit = defineEmits<{ close: []; create: [input: TransportRentalInput]; closeRental: [endedAt: string] }>()
const courierId = ref('')
const startedAt = ref('')
const endedAt = ref(toLocalInput(new Date()))
const historicalEnd = ref('')
const fieldError = ref('')

function toLocalInput(date: Date) {
  const offset = date.getTimezoneOffset() * 60_000
  return new Date(date.getTime() - offset).toISOString().slice(0, 16)
}

function iso(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date.toISOString()
}

function submit() {
  fieldError.value = ''
  if (props.rental) {
    const end = iso(endedAt.value)
    if (!end || new Date(end) <= new Date(props.rental.startedAt)) {
      fieldError.value = 'Дата завершения должна быть позже начала.'
      void nextTick(() => document.getElementById('rental-endedAt')?.focus())
      return
    }
    emit('closeRental', end)
    return
  }

  const start = iso(startedAt.value)
  const end = historicalEnd.value ? iso(historicalEnd.value) : null
  if (!courierId.value) fieldError.value = 'Выберите курьера.'
  else if (!start || new Date(start) > new Date()) fieldError.value = 'Укажите дату начала не в будущем.'
  else if (props.requireHistorical && !historicalEnd.value) fieldError.value = 'При действующей аренде можно добавить только завершённый прошлый период.'
  else if (historicalEnd.value && (!end || new Date(end) > new Date() || new Date(end) <= new Date(start))) fieldError.value = 'Дата завершения должна быть позже начала и не в будущем.'
  if (fieldError.value || !start) return
  emit('create', { courierId: courierId.value, startedAt: start, endedAt: end })
}
</script>

<template>
  <AppModal label-id="rentalFormTitle" modal-class="modal-confirm" data-od-id="rental-form-dialog" @close="$emit('close')">
    <div class="modal-header"><div class="row-between"><div><h2 id="rentalFormTitle">{{ rental ? 'Завершить аренду' : 'Выдать велосипед' }}</h2><p>{{ rental ? 'Укажите фактическое время возврата' : 'Можно внести активную или завершённую аренду' }}</p></div><button class="btn btn-ghost btn-icon" type="button" aria-label="Закрыть" :disabled="saving" @click="$emit('close')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg></button></div></div>
    <form novalidate @submit.prevent="submit"><div class="modal-body">
      <div v-if="!rental" class="form-grid form-grid-single"><div class="field"><label class="required">Курьер</label><CourierPicker v-model="courierId" /></div><div class="field"><label class="required" for="rental-startedAt">Начало аренды</label><input id="rental-startedAt" v-model="startedAt" class="input num" type="datetime-local" /></div><div class="field"><label :class="{ required: requireHistorical }" for="rental-historicalEnd">Завершение{{ requireHistorical ? '' : ', если это история' }}</label><input id="rental-historicalEnd" v-model="historicalEnd" class="input num" type="datetime-local" /></div></div>
      <div v-else class="field"><label class="required" for="rental-endedAt">Дата и время возврата</label><input id="rental-endedAt" v-model="endedAt" class="input num" type="datetime-local" /></div>
      <p v-if="fieldError" class="form-api-error" role="alert">{{ fieldError }}</p><p v-if="error" class="form-api-error" role="alert">{{ error }}</p>
    </div><div class="modal-footer"><button class="btn btn-secondary" type="button" :disabled="saving" @click="$emit('close')">Отмена</button><button class="btn btn-primary" type="submit" :disabled="saving">{{ saving ? 'Сохраняем…' : rental ? 'Завершить аренду' : 'Сохранить аренду' }}</button></div></form>
  </AppModal>
</template>
