<script setup lang="ts">
import { nextTick, reactive } from 'vue'
import type { TransportComponent, TransportComponentInput } from '../../types/transport'
import AppModal from '../ui/AppModal.vue'
import { validateComponentInput } from './transportForm'

const props = defineProps<{ component?: TransportComponent | null; saving: boolean; error: string }>()
const emit = defineEmits<{ close: []; save: [input: TransportComponentInput] }>()
const form = reactive<TransportComponentInput>({ name: props.component?.name ?? '', unitPrice: props.component?.unitPrice ?? '', quantity: props.component?.quantity ?? 1 })
const errors = reactive<Record<string, string>>({})

function submit() {
  const result = validateComponentInput(form)
  for (const key of Object.keys(errors)) delete errors[key]
  Object.assign(errors, result.errors)
  if (!result.value) {
    const first = ['name', 'unitPrice', 'quantity'].find((key) => errors[key])
    void nextTick(() => document.getElementById(`component-${first}`)?.focus())
    return
  }
  emit('save', result.value)
}
</script>

<template>
  <AppModal label-id="componentFormTitle" modal-class="modal-confirm" data-od-id="component-form-dialog" @close="$emit('close')">
    <div class="modal-header"><div class="row-between"><div><h2 id="componentFormTitle">{{ component ? 'Изменить комплектацию' : 'Добавить в комплектацию' }}</h2><p>Текущее оснащение велосипеда</p></div><button class="btn btn-ghost btn-icon" type="button" aria-label="Закрыть" :disabled="saving" @click="$emit('close')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg></button></div></div>
    <form novalidate @submit.prevent="submit"><div class="modal-body"><div class="form-grid form-grid-single">
      <div class="field" :class="{ invalid: errors.name }"><label class="required" for="component-name">Название</label><input id="component-name" v-model="form.name" class="input" maxlength="128" /><span class="field-error">{{ errors.name }}</span></div>
      <div class="form-grid"><div class="field" :class="{ invalid: errors.unitPrice }"><label class="required" for="component-unitPrice">Цена за единицу, CZK</label><input id="component-unitPrice" v-model="form.unitPrice" class="input num" inputmode="decimal" /><span class="field-error">{{ errors.unitPrice }}</span></div><div class="field" :class="{ invalid: errors.quantity }"><label class="required" for="component-quantity">Количество</label><input id="component-quantity" v-model.number="form.quantity" class="input num" type="number" min="1" step="1" /><span class="field-error">{{ errors.quantity }}</span></div></div>
    </div><p v-if="error" class="form-api-error" role="alert">{{ error }}</p></div><div class="modal-footer"><button class="btn btn-secondary" type="button" :disabled="saving" @click="$emit('close')">Отмена</button><button class="btn btn-primary" type="submit" :disabled="saving">{{ saving ? 'Сохраняем…' : 'Сохранить' }}</button></div></form>
  </AppModal>
</template>
