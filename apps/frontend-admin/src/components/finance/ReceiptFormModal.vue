<script setup lang="ts">
import { nextTick, ref } from 'vue'
import type { Receipt, ReceiptFormInput, ReceiptTag } from '../../types/receipt'
import AppModal from '../ui/AppModal.vue'
import {
  normalizeReceiptAmount,
  validateReceiptAmount,
  validateReceiptFile,
} from './receiptForm'
import { todayInPrague, validateReceiptDate } from './receiptDate'

const props = defineProps<{
  receipt?: Receipt | null
  saving: boolean
  error: string
  tags: ReceiptTag[]
}>()

const emit = defineEmits<{
  close: []
  save: [input: ReceiptFormInput]
}>()

const amount = ref(props.receipt?.amount ?? '')
const date = ref(props.receipt?.date ?? todayInPrague())
const tagId = ref(props.receipt?.tagId ?? '')
const file = ref<File | null>(null)
const amountError = ref('')
const dateError = ref('')
const fileError = ref('')

function selectFile(event: Event) {
  const input = event.currentTarget as HTMLInputElement
  const selected = input.files?.[0] ?? null
  const error = validateReceiptFile(selected, false)
  fileError.value = error
  if (error) {
    input.value = ''
    file.value = null
    return
  }
  file.value = selected
}

function submit() {
  amountError.value = validateReceiptAmount(amount.value)
  dateError.value = validateReceiptDate(date.value)
  fileError.value = validateReceiptFile(file.value, !props.receipt)
  if (amountError.value || dateError.value || fileError.value) {
    const target = amountError.value
      ? 'receipt-amount'
      : dateError.value
        ? 'receipt-date'
        : 'receipt-file'
    void nextTick(() => document.getElementById(target)?.focus())
    return
  }
  emit('save', {
    amount: normalizeReceiptAmount(amount.value),
    date: date.value,
    tagId: tagId.value || null,
    file: file.value,
  })
}
</script>

<template>
  <AppModal
    label-id="receiptFormTitle"
    data-od-id="receipt-form-dialog"
    @close="$emit('close')"
  >
    <div class="modal-header">
      <div class="row-between">
        <div>
          <p class="eyebrow">Finance</p>
          <h2 id="receiptFormTitle">{{ receipt ? 'Редактирование чека' : 'Новый чек' }}</h2>
          <p>{{ receipt ? 'Дату и сумму можно изменить, файл — заменить.' : 'Укажите дату, сумму в CZK и загрузите файл.' }}</p>
        </div>
        <button
          class="btn btn-ghost btn-icon"
          type="button"
          aria-label="Закрыть"
          :disabled="saving"
          @click="$emit('close')"
        >
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
            <h3>Данные чека</h3>
            <p>Дата используется для статистики по месяцам, сумма сохраняется с точностью до двух знаков.</p>
          </div>
          <div class="form-grid">
            <div class="field" :class="{ invalid: dateError }">
              <label class="required" for="receipt-date">Дата чека</label>
              <input
                id="receipt-date"
                v-model="date"
                class="input num"
                type="date"
                :aria-invalid="Boolean(dateError)"
                aria-describedby="receipt-date-error"
              />
              <span id="receipt-date-error" class="field-error" role="alert">{{ dateError }}</span>
            </div>
            <div class="field" :class="{ invalid: amountError }">
              <label class="required" for="receipt-amount">Сумма, CZK</label>
              <input
                id="receipt-amount"
                v-model="amount"
                class="input num"
                inputmode="decimal"
                placeholder="1250.00"
                :aria-invalid="Boolean(amountError)"
                aria-describedby="receipt-amount-error"
              />
              <span id="receipt-amount-error" class="field-error" role="alert">{{ amountError }}</span>
            </div>
            <div class="field">
              <label for="receipt-tag">Тип расхода</label>
              <select id="receipt-tag" v-model="tagId" class="select" :disabled="saving">
                <option value="">Без тега</option>
                <option v-for="tag in tags" :key="tag.id" :value="tag.id">{{ tag.name }}</option>
              </select>
            </div>
          </div>
        </div>

        <div class="form-section">
          <div class="form-section-title">
            <h3>{{ receipt ? 'Замена файла' : 'Файл чека' }}</h3>
            <p>{{ receipt ? 'Оставьте поле пустым, чтобы сохранить текущий файл.' : 'Файл будет загружен напрямую в защищённое хранилище.' }}</p>
          </div>
          <div class="file-control" :class="{ invalid: fileError }">
            <div class="file-copy">
              <strong>{{ file?.name || (receipt ? 'Текущий файл без изменений' : 'Выберите файл') }}</strong>
              <span>PDF, JPG, PNG или WebP · до 25 МБ</span>
              <span id="receipt-file-error" class="file-error" role="alert">{{ fileError }}</span>
            </div>
            <input
              id="receipt-file"
              type="file"
              :aria-label="receipt ? 'Заменить файл чека' : 'Файл чека'"
              :aria-invalid="Boolean(fileError)"
              aria-describedby="receipt-file-error"
              accept=".pdf,.jpg,.jpeg,.png,.webp"
              :disabled="saving"
              @change="selectFile"
            />
          </div>
        </div>
        <p v-if="error" class="form-api-error" role="alert">{{ error }}</p>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" type="button" :disabled="saving" @click="$emit('close')">
          Отмена
        </button>
        <button class="btn btn-primary" type="submit" data-od-id="save-receipt" :disabled="saving">
          {{ saving ? 'Сохраняем…' : receipt ? 'Сохранить' : 'Добавить чек' }}
        </button>
      </div>
    </form>
  </AppModal>
</template>
