<script setup lang="ts">
import { nextTick, reactive } from 'vue'
import type { Transport, TransportInput } from '../../types/transport'
import AppModal from '../ui/AppModal.vue'
import { validateTransportInput, type TransportFormInput } from './transportForm'

const props = defineProps<{
  transport?: Transport | null
  saving: boolean
  error: string
}>()

const emit = defineEmits<{
  close: []
  save: [input: TransportInput]
}>()

const form = reactive<TransportFormInput>({
  type: props.transport?.type ?? 'e-bike',
  model: props.transport?.model ?? '',
  serialNumber: props.transport?.serialNumber ?? '',
  ordinalNumber: props.transport?.ordinalNumber?.toString() ?? '',
  color: props.transport?.color ?? '',
  depositRequired: props.transport?.depositRequired ?? false,
  depositAmount: props.transport?.depositAmount ?? '',
  rentalPrice: props.transport?.rentalPrice ?? '',
  comment: props.transport?.comment ?? '',
  debtAmount: props.transport?.debtAmount ?? '0.00',
})
const errors = reactive<Record<string, string>>({})

function submit() {
  const result = validateTransportInput(form)
  for (const key of Object.keys(errors)) delete errors[key]
  Object.assign(errors, result.errors)
  if (!result.value) {
    const first = ['type', 'model', 'serialNumber', 'ordinalNumber', 'color', 'rentalPrice', 'debtAmount', 'depositAmount', 'comment'].find((key) => errors[key])
    void nextTick(() => document.getElementById(`bike-${first}`)?.focus())
    return
  }
  emit('save', result.value)
}
</script>

<template>
  <AppModal label-id="transportFormTitle" data-od-id="bike-form-dialog" @close="$emit('close')">
    <div class="modal-header"><div class="row-between"><div><h2 id="transportFormTitle">{{ transport ? 'Редактирование велосипеда' : 'Новый велосипед' }}</h2><p>{{ transport ? transport.serialNumber : 'Учётная карточка транспорта' }}</p></div><button class="btn btn-ghost btn-icon" type="button" aria-label="Закрыть" :disabled="saving" @click="$emit('close')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg></button></div></div>
    <form novalidate @submit.prevent="submit">
      <div class="modal-body">
        <div class="form-section"><div class="form-section-title"><h3>Идентификация</h3><p>Тип нормализуется в нижний регистр, серийный номер — в верхний.</p></div>
          <div class="form-grid">
            <div class="field" :class="{ invalid: errors.type }"><label class="required" for="bike-type">Тип</label><input id="bike-type" v-model="form.type" class="input" maxlength="64" placeholder="e-bike" /><span class="field-error">{{ errors.type }}</span></div>
            <div class="field" :class="{ invalid: errors.model }"><label class="required" for="bike-model">Модель</label><input id="bike-model" v-model="form.model" class="input" maxlength="128" /><span class="field-error">{{ errors.model }}</span></div>
            <div class="field" :class="{ invalid: errors.serialNumber }"><label class="required" for="bike-serialNumber">Серийный номер</label><input id="bike-serialNumber" v-model="form.serialNumber" class="input num" maxlength="64" /><span class="field-error">{{ errors.serialNumber }}</span></div>
            <div class="field" :class="{ invalid: errors.ordinalNumber }"><label for="bike-ordinalNumber">Порядковый номер</label><input id="bike-ordinalNumber" v-model="form.ordinalNumber" class="input num" inputmode="numeric" :aria-invalid="Boolean(errors.ordinalNumber)" aria-describedby="bike-ordinalNumber-error" /><span id="bike-ordinalNumber-error" class="field-error">{{ errors.ordinalNumber }}</span></div>
            <div class="field" :class="{ invalid: errors.color }"><label class="required" for="bike-color">Цвет</label><input id="bike-color" v-model="form.color" class="input" maxlength="64" /><span class="field-error">{{ errors.color }}</span></div>
          </div>
        </div>
        <div class="form-section"><div class="form-section-title"><h3>Условия аренды</h3><p>Денежные значения указываются в CZK.</p></div>
          <div class="form-grid">
            <div class="field" :class="{ invalid: errors.rentalPrice }"><label class="required" for="bike-rentalPrice">Ставка аренды</label><input id="bike-rentalPrice" v-model="form.rentalPrice" class="input num" inputmode="decimal" placeholder="1250.00" /><span class="field-error">{{ errors.rentalPrice }}</span></div>
            <div class="field" :class="{ invalid: errors.debtAmount }"><label class="required" for="bike-debtAmount">Задолженность</label><input id="bike-debtAmount" v-model="form.debtAmount" class="input num" inputmode="decimal" placeholder="0.00" /><span class="field-error">{{ errors.debtAmount }}</span></div>
            <label class="checkbox-row"><input v-model="form.depositRequired" type="checkbox" /><span class="checkbox-copy"><strong>Требуется залог</strong><span>Сумма обязательна только при включённом залоге.</span></span></label>
            <div v-if="form.depositRequired" class="field" :class="{ invalid: errors.depositAmount }"><label class="required" for="bike-depositAmount">Сумма залога</label><input id="bike-depositAmount" v-model="form.depositAmount" class="input num" inputmode="decimal" placeholder="500.00" /><span class="field-error">{{ errors.depositAmount }}</span></div>
            <div class="field field-wide" :class="{ invalid: errors.comment }"><label for="bike-comment">Комментарий</label><textarea id="bike-comment" v-model="form.comment" class="textarea" maxlength="2000" rows="4" placeholder="Состояние, обслуживание или другие примечания"></textarea><span class="field-error">{{ errors.comment }}</span></div>
          </div>
        </div>
        <p v-if="error" class="form-api-error" role="alert">{{ error }}</p>
      </div>
      <div class="modal-footer"><button class="btn btn-secondary" type="button" :disabled="saving" @click="$emit('close')">Отмена</button><button class="btn btn-primary" type="submit" data-od-id="save-bike" :disabled="saving">{{ saving ? 'Сохраняем…' : transport ? 'Сохранить' : 'Добавить велосипед' }}</button></div>
    </form>
  </AppModal>
</template>
