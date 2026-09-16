<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type {
  Courier,
  CourierBulkAction,
  CourierBulkStatusInput,
  DeliveryPlatform,
  PlatformStatus,
} from '../../types/courier'
import AppModal from '../ui/AppModal.vue'

const props = defineProps<{
  action: CourierBulkAction
  couriers: Courier[]
  busy: boolean
  error: string
}>()

const emit = defineEmits<{
  close: []
  delete: []
  status: [input: CourierBulkStatusInput]
  clearError: []
}>()

const platform = ref<DeliveryPlatform | ''>('')
const status = ref<PlatformStatus | ''>('')
const missingPlatform = computed(() => {
  if (!platform.value) return []
  return props.couriers.filter(
    (courier) => !courier.platforms.some((account) => account.platform === platform.value),
  )
})
const canSubmit = computed(
  () => !props.busy && props.couriers.length > 0 && (
    props.action === 'delete' || (platform.value && status.value && !missingPlatform.value.length)
  ),
)

watch([platform, status], () => emit('clearError'))

function submit() {
  if (!canSubmit.value) return
  if (props.action === 'delete') {
    emit('delete')
  } else if (platform.value && status.value) {
    emit('status', { platform: platform.value, status: status.value })
  }
}
</script>

<template>
  <AppModal
    label-id="courierBulkTitle"
    modal-class="modal-confirm"
    data-od-id="courier-bulk-dialog"
    @close="$emit('close')"
  >
    <form :aria-busy="busy" @submit.prevent="submit">
      <div class="modal-header">
        <div class="row-between">
          <div>
            <p class="eyebrow">Массовая операция</p>
            <h2 id="courierBulkTitle">
              {{ action === 'delete' ? 'Удалить выбранных курьеров?' : 'Изменить статус платформы' }}
            </h2>
          </div>
          <button
            class="btn btn-ghost btn-icon"
            type="button"
            aria-label="Закрыть"
            :disabled="busy"
            @click="$emit('close')"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
              <path d="m6 6 12 12M18 6 6 18" />
            </svg>
          </button>
        </div>
      </div>
      <div class="modal-body">
        <p>Выбрано курьеров: <strong>{{ couriers.length }}</strong>, включая другие страницы.</p>
        <ul class="courier-bulk-list" aria-label="Выбранные курьеры">
          <li v-for="courier in couriers" :key="courier.id">
            <strong>{{ courier.fullName }}</strong> <span class="meta">{{ courier.email }}</span>
          </li>
        </ul>
        <p v-if="action === 'delete'">
          Профили, регистрации на платформах и связанные документы будут удалены без возможности восстановления.
          Если у курьера есть подписанный договор аренды, вся операция будет отменена.
        </p>
        <template v-else>
          <p>Статус изменится у выбранной платформы. Она должна быть подключена у всех выбранных курьеров.</p>
          <div class="form-grid">
            <div class="field">
              <label for="courier-bulk-platform">Платформа</label>
              <select
                id="courier-bulk-platform"
                v-model="platform"
                class="select"
                required
                :disabled="busy"
                :aria-invalid="missingPlatform.length > 0"
                :aria-describedby="missingPlatform.length ? 'courier-bulk-missing' : undefined"
              >
                <option disabled value="">Выберите платформу</option>
                <option value="bolt_food">Bolt Food</option>
                <option value="foodora">Foodora</option>
                <option value="wolt">Wolt</option>
              </select>
            </div>
            <div class="field">
              <label for="courier-bulk-status">Новый статус</label>
              <select id="courier-bulk-status" v-model="status" class="select" required :disabled="busy">
                <option disabled value="">Выберите статус</option>
                <option value="pending">Ожидает</option>
                <option value="active">Активен</option>
                <option value="inactive">Неактивен</option>
                <option value="problem">Проблема</option>
              </select>
            </div>
          </div>
          <p v-if="missingPlatform.length" id="courier-bulk-missing" class="form-api-error" role="alert">
            Нет регистрации на этой платформе: {{ missingPlatform.map((courier) => courier.fullName).join(', ') }}.
            Выберите другую платформу или измените выбор курьеров.
          </p>
        </template>
        <p v-if="error" class="form-api-error" role="alert">{{ error }}</p>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" type="button" :disabled="busy" @click="$emit('close')">
          Отмена
        </button>
        <button
          class="btn"
          :class="action === 'delete' ? 'btn-danger' : 'btn-primary'"
          type="submit"
          :disabled="!canSubmit"
        >
          {{ busy ? 'Выполняем…' : action === 'delete' ? 'Удалить выбранных' : 'Изменить статус' }}
        </button>
      </div>
    </form>
  </AppModal>
</template>
