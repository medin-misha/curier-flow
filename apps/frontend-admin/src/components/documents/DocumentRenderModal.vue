<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { getCourier, listCouriers } from '../../api/couriers'
import {
  getTransport,
  listTransportRentals,
  listTransports,
} from '../../api/transports'
import type { Courier } from '../../types/courier'
import type {
  DocumentModelGroup,
  DocumentRenderValues,
  DocumentTemplate,
  DocumentValueSource,
} from '../../types/document'
import type { TransportListItem, TransportRental } from '../../types/transport'
import AppModal from '../ui/AppModal.vue'
import { documentModelValues } from './documentModelFields'

const props = defineProps<{
  template: DocumentTemplate
  rendering: boolean
  error: string
}>()

const emit = defineEmits<{
  close: []
  render: [values: DocumentRenderValues]
}>()

const values = reactive<DocumentRenderValues>(
  Object.fromEntries(
    Object.entries(props.template.fields).map(([group, fields]) => [
      group,
      Object.fromEntries(fields.map((field) => [field, ''])),
    ]),
  ),
)
const sources = reactive<Record<string, Record<string, DocumentValueSource>>>(
  Object.fromEntries(
    Object.entries(props.template.fields).map(([group, fields]) => [
      group,
      Object.fromEntries(fields.map((field) => [field, 'empty'])),
    ]),
  ),
)

const needsCourier = 'courier' in props.template.fields
const needsRental = 'transport_courier' in props.template.fields
const needsTransport = 'transport' in props.template.fields || needsRental

const courierId = ref('')
const courierQuery = ref('')
const couriers = ref<Courier[]>([])
const selectedCourier = ref<Courier | null>(null)
const courierCursor = ref<string | null>(null)
const courierLoading = ref(false)
const courierHydrating = ref(false)
const courierError = ref('')

const transportId = ref('')
const transports = ref<TransportListItem[]>([])
const transportCursor = ref<string | null>(null)
const transportLoading = ref(false)
const transportHydrating = ref(false)
const transportError = ref('')

const rentalId = ref('')
const rentals = ref<TransportRental[]>([])
const rentalCursor = ref<string | null>(null)
const rentalLoading = ref(false)
const rentalError = ref('')
const selectedRental = ref<TransportRental | null>(null)

let courierLoadSequence = 0
let courierSelectionSequence = 0
let transportLoadSequence = 0
let transportSelectionSequence = 0
let rentalLoadSequence = 0
const courierCache = new Map<string, Courier>()
const transportCache = new Map<string, Awaited<ReturnType<typeof getTransport>>>()

const contextLoading = computed(
  () => courierHydrating.value || transportHydrating.value,
)
const relationError = computed(() => {
  const rental = selectedRental.value
  if (!rental) return ''
  if (transportId.value && rental.transportId !== transportId.value) {
    return 'Выбранная аренда относится к другому транспорту.'
  }
  if (courierId.value && rental.courierId !== courierId.value) {
    return 'Выбранная аренда относится к другому курьеру.'
  }
  return ''
})

function fieldId(group: string, field: string) {
  return `document-value-${group}-${field}`.replace(/[^a-zA-Z0-9_-]/g, '-')
}

function updateValue(group: string, field: string, event: Event) {
  const groupValues = values[group]
  if (!groupValues) return
  groupValues[field] = (event.currentTarget as HTMLInputElement).value
  if (sources[group]) sources[group][field] = 'manual'
}

function clearModelValues(group: DocumentModelGroup) {
  const groupValues = values[group]
  const groupSources = sources[group]
  if (!groupValues || !groupSources) return
  for (const field of props.template.fields[group] ?? []) {
    if (groupSources[field] === 'model') {
      groupValues[field] = ''
      groupSources[field] = 'empty'
    }
  }
}

function hydrate(group: DocumentModelGroup, model: unknown) {
  const groupValues = values[group]
  const groupSources = sources[group]
  if (!groupValues || !groupSources) return
  const modelValues = documentModelValues(group, props.template.fields[group] ?? [], model)
  for (const [field, value] of Object.entries(modelValues)) {
    if (groupSources[field] === 'manual') continue
    groupValues[field] = value
    groupSources[field] = 'model'
  }
}

function sourceLabel(group: string, field: string) {
  if (sources[group]?.[field] !== 'model') return 'Вручную'
  if (group === 'courier') return 'Курьер'
  if (group === 'transport') return 'Транспорт'
  return 'Аренда'
}

async function loadCouriers(reset: boolean) {
  const sequence = ++courierLoadSequence
  courierLoading.value = true
  courierError.value = ''
  try {
    const result = await listCouriers({
      cursor: reset ? null : courierCursor.value,
      limit: 50,
      query: courierQuery.value,
    })
    if (sequence !== courierLoadSequence) return
    const items = reset ? result.items : [...couriers.value, ...result.items]
    if (selectedCourier.value && !items.some((courier) => courier.id === selectedCourier.value?.id)) {
      items.unshift(selectedCourier.value)
    }
    couriers.value = items
    courierCursor.value = result.nextCursor
  } catch {
    if (sequence === courierLoadSequence) courierError.value = 'Не удалось загрузить курьеров.'
  } finally {
    if (sequence === courierLoadSequence) courierLoading.value = false
  }
}

async function selectCourier() {
  const sequence = ++courierSelectionSequence
  clearModelValues('courier')
  courierError.value = ''
  selectedCourier.value = couriers.value.find((courier) => courier.id === courierId.value) ?? null
  if (!courierId.value) {
    courierHydrating.value = false
    return
  }
  courierHydrating.value = true
  try {
    const courier = courierCache.get(courierId.value) ?? await getCourier(courierId.value)
    courierCache.set(courier.id, courier)
    if (sequence === courierSelectionSequence) {
      selectedCourier.value = courier
      hydrate('courier', courier)
    }
  } catch {
    if (sequence === courierSelectionSequence) courierError.value = 'Не удалось загрузить курьера.'
  } finally {
    if (sequence === courierSelectionSequence) courierHydrating.value = false
  }
}

async function loadTransports(reset: boolean) {
  const sequence = ++transportLoadSequence
  transportLoading.value = true
  transportError.value = ''
  try {
    const result = await listTransports({
      cursor: reset ? null : transportCursor.value,
      limit: 50,
      filters: { type: '', serialNumber: '', courierId: '', availability: '' },
    })
    if (sequence !== transportLoadSequence) return
    transports.value = reset ? result.items : [...transports.value, ...result.items]
    transportCursor.value = result.nextCursor
  } catch {
    if (sequence === transportLoadSequence) transportError.value = 'Не удалось загрузить транспорт.'
  } finally {
    if (sequence === transportLoadSequence) transportLoading.value = false
  }
}

async function selectTransport() {
  const sequence = ++transportSelectionSequence
  clearModelValues('transport')
  clearModelValues('transport_courier')
  rentalId.value = ''
  selectedRental.value = null
  rentals.value = []
  rentalCursor.value = null
  transportError.value = ''
  if (!transportId.value) {
    rentalLoadSequence += 1
    rentalLoading.value = false
    transportHydrating.value = false
    return
  }

  transportHydrating.value = true
  const cachedTransport = transportCache.get(transportId.value)
  const detailRequest = cachedTransport ? Promise.resolve(cachedTransport) : getTransport(transportId.value)
  if (needsRental) void loadRentals(true)
  try {
    const transport = await detailRequest
    transportCache.set(transport.id, transport)
    if (sequence === transportSelectionSequence) hydrate('transport', transport)
  } catch {
    if (sequence === transportSelectionSequence) {
      transportError.value = 'Не удалось загрузить транспорт.'
    }
  } finally {
    if (sequence === transportSelectionSequence) transportHydrating.value = false
  }
}

async function loadRentals(reset: boolean) {
  if (!transportId.value) return
  const requestedTransportId = transportId.value
  const sequence = ++rentalLoadSequence
  rentalLoading.value = true
  rentalError.value = ''
  try {
    const result = await listTransportRentals(requestedTransportId, {
      cursor: reset ? null : rentalCursor.value,
      limit: 50,
    })
    if (sequence !== rentalLoadSequence || requestedTransportId !== transportId.value) return
    rentals.value = reset ? result.items : [...rentals.value, ...result.items]
    rentalCursor.value = result.nextCursor
  } catch {
    if (sequence === rentalLoadSequence) rentalError.value = 'Не удалось загрузить аренды.'
  } finally {
    if (sequence === rentalLoadSequence) rentalLoading.value = false
  }
}

function selectRental() {
  clearModelValues('transport_courier')
  selectedRental.value = rentals.value.find((rental) => rental.id === rentalId.value) ?? null
  if (selectedRental.value) hydrate('transport_courier', selectedRental.value)
}

function rentalLabel(rental: TransportRental) {
  const started = rental.startedAt.slice(0, 10)
  const ended = rental.endedAt?.slice(0, 10) ?? 'сейчас'
  return `${started} — ${ended} · ${rental.courierId}`
}

function submit() {
  if (relationError.value || contextLoading.value) return
  emit(
    'render',
    Object.fromEntries(
      Object.entries(values).map(([group, fields]) => [group, { ...fields }]),
    ),
  )
}

onMounted(() => {
  if (needsCourier) void loadCouriers(true)
  if (needsTransport) void loadTransports(true)
})
</script>

<template>
  <AppModal
    label-id="documentRenderTitle"
    modal-class="modal-detail"
    data-od-id="document-render-dialog"
    @close="$emit('close')"
  >
    <div class="modal-header">
      <div class="row-between">
        <div>
          <p class="eyebrow">Генерация DOCX</p>
          <h2 id="documentRenderTitle">{{ template.name }}</h2>
          <p>Выберите связанные данные или заполните значения вручную.</p>
        </div>
        <button class="btn btn-ghost btn-icon" type="button" aria-label="Закрыть" :disabled="rendering" @click="$emit('close')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
            <path d="m6 6 12 12M18 6 6 18" />
          </svg>
        </button>
      </div>
    </div>

    <form @submit.prevent="submit">
      <div class="modal-body">
        <section v-if="needsCourier || needsTransport" class="document-context">
          <div class="form-section-title">
            <h3>Данные из реестров</h3>
            <p>Выбор необязателен. Автоматические значения можно исправить ниже.</p>
          </div>

          <div class="form-grid">
            <div v-if="needsCourier" class="field field-wide">
              <label for="document-courier">Курьер</label>
              <div class="document-context-search">
                <input v-model="courierQuery" class="input" type="search" placeholder="Точное имя, email или телефон" :disabled="courierLoading || rendering" @keydown.enter.prevent="loadCouriers(true)" />
                <button class="btn btn-secondary" type="button" :disabled="courierLoading || rendering" @click="loadCouriers(true)">Найти</button>
              </div>
              <select id="document-courier" v-model="courierId" class="select" :disabled="courierLoading || courierHydrating || rendering" @change="selectCourier">
                <option value="">Не выбран, заполнить вручную</option>
                <option v-for="courier in couriers" :key="courier.id" :value="courier.id">{{ courier.fullName }} · {{ courier.email || courier.id }}</option>
              </select>
              <button v-if="courierCursor" class="document-load-more" type="button" :disabled="courierLoading" @click="loadCouriers(false)">Загрузить ещё</button>
              <span v-if="courierError" class="field-error" role="alert">{{ courierError }}</span>
            </div>

            <div v-if="needsTransport" class="field field-wide">
              <label for="document-transport">Транспорт</label>
              <select id="document-transport" v-model="transportId" class="select" :disabled="transportLoading || transportHydrating || rendering" @change="selectTransport">
                <option value="">Не выбран, заполнить вручную</option>
                <option v-for="transport in transports" :key="transport.id" :value="transport.id">{{ transport.model }} · {{ transport.serialNumber }}</option>
              </select>
              <button v-if="transportCursor" class="document-load-more" type="button" :disabled="transportLoading" @click="loadTransports(false)">Загрузить ещё</button>
              <span v-if="transportError" class="field-error" role="alert">{{ transportError }}</span>
            </div>

            <div v-if="needsRental" class="field field-wide">
              <label for="document-rental">Аренда транспорта</label>
              <select id="document-rental" v-model="rentalId" class="select" :disabled="!transportId || rentalLoading || rendering" @change="selectRental">
                <option value="">Не выбрана, заполнить вручную</option>
                <option v-for="rental in rentals" :key="rental.id" :value="rental.id">{{ rentalLabel(rental) }}</option>
              </select>
              <span v-if="!transportId" class="render-field-path">Сначала выберите транспорт.</span>
              <button v-if="rentalCursor" class="document-load-more" type="button" :disabled="rentalLoading" @click="loadRentals(false)">Загрузить ещё</button>
              <span v-if="rentalError" class="field-error" role="alert">{{ rentalError }}</span>
            </div>
          </div>
          <p v-if="relationError" class="form-api-error" role="alert">{{ relationError }}</p>
        </section>

        <section v-for="(fields, group) in template.fields" :key="group" class="render-field-group">
          <div class="form-section-title">
            <h3>{{ group }}</h3>
            <p>Группа {{ group }} · {{ fields.length }} полей</p>
          </div>
          <div class="form-grid">
            <div v-for="field in fields" :key="field" class="field">
              <label :for="fieldId(String(group), field)">{{ field }}</label>
              <input
                :id="fieldId(String(group), field)"
                class="input"
                type="text"
                maxlength="10000"
                :value="values[String(group)]?.[field]"
                :disabled="rendering"
                :placeholder="`{${String(group)}.${field}}`"
                @input="updateValue(String(group), field, $event)"
              />
              <span class="render-field-path num">{{ group }}.{{ field }} · {{ sourceLabel(String(group), field) }}</span>
            </div>
          </div>
        </section>
        <p v-if="error" class="form-api-error" role="alert">{{ error }}</p>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" type="button" :disabled="rendering" @click="$emit('close')">
          Назад
        </button>
        <button class="btn btn-primary" type="submit" data-od-id="download-rendered-document" :disabled="rendering || contextLoading || Boolean(relationError)">
          {{ rendering ? 'Формируем…' : 'Сформировать и скачать' }}
        </button>
      </div>
    </form>
  </AppModal>
</template>
