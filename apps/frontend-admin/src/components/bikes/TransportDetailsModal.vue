<script setup lang="ts">
import { computed } from 'vue'
import type { Transport, TransportComponent, TransportRental } from '../../types/transport'
import AppModal from '../ui/AppModal.vue'

const props = defineProps<{
  transport: Transport
  rentals: TransportRental[]
  courierNames: Record<string, string>
  rentalLoading: boolean
  rentalsNext: boolean
  busy: boolean
  error: string
  downloadingFileIds: string[]
}>()

defineEmits<{
  close: []
  edit: []
  delete: []
  addComponent: []
  editComponent: [component: TransportComponent]
  deleteComponent: [component: TransportComponent]
  createRental: []
  closeRental: [rental: TransportRental]
  attachContract: [rental: TransportRental]
  downloadContract: [rental: TransportRental]
  loadMoreRentals: []
}>()

const sortedComponents = computed(() =>
  [...props.transport.components].sort((left, right) => left.name.localeCompare(right.name, 'ru')),
)

function formatDate(value: string | null) {
  if (!value) return 'По настоящее время'
  return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

function courierName(id: string) {
  return props.courierNames[id] || id
}
</script>

<template>
  <AppModal label-id="bikeDetailTitle" modal-class="modal-detail modal-transport" data-od-id="bike-detail-dialog" @close="$emit('close')">
    <div class="modal-header"><div class="row-between"><div><p class="eyebrow">{{ transport.type }}</p><h2 id="bikeDetailTitle">{{ transport.model }}</h2><p class="num">{{ transport.serialNumber }} · ID {{ transport.id }}</p></div><button class="btn btn-ghost btn-icon" type="button" aria-label="Закрыть" :disabled="busy" @click="$emit('close')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg></button></div></div>
    <div class="modal-body">
      <div class="detail-grid">
        <div class="detail-item"><span>Цвет</span><strong>{{ transport.color }}</strong></div>
        <div class="detail-item"><span>Доступность</span><strong>{{ transport.isAvailable ? 'Свободен' : 'Выдан' }}</strong></div>
        <div class="detail-item"><span>Ставка аренды</span><strong class="num">{{ transport.rentalPrice }} Kč</strong></div>
        <div class="detail-item"><span>Залог</span><strong class="num">{{ transport.depositRequired ? `${transport.depositAmount} Kč` : 'Не требуется' }}</strong></div>
        <div class="detail-item"><span>Задолженность</span><strong class="num">{{ transport.debtAmount }} Kč</strong></div>
      </div>

      <div class="detail-group">
        <h3>Комментарий</h3>
        <p class="transport-comment">{{ transport.comment || 'Не указан' }}</p>
      </div>

      <div class="detail-group">
        <div class="row-between"><div><h3>Текущая аренда</h3><p class="admin-state-note">Доступность вычисляется по активной аренде.</p></div><button class="btn btn-primary btn-compact" type="button" @click="$emit('createRental')">{{ transport.isAvailable ? 'Выдать курьеру' : 'Добавить прошлый период' }}</button></div>
        <div v-if="transport.activeRental" class="rental-current">
          <div><strong>{{ courierName(transport.activeRental.courierId) }}</strong><span class="num">с {{ formatDate(transport.activeRental.startedAt) }}</span></div>
          <button class="btn btn-secondary btn-compact" type="button" @click="$emit('closeRental', transport.activeRental)">Завершить аренду</button>
        </div>
        <div v-else class="document-empty"><strong>Велосипед свободен</strong><span>Активной аренды нет.</span></div>
      </div>

      <div class="detail-group">
        <div class="row-between"><div><h3>Комплектация</h3><p class="admin-state-note">Текущее оснащение и его учётная стоимость.</p></div><button class="btn btn-secondary btn-compact" type="button" @click="$emit('addComponent')">Добавить позицию</button></div>
        <div v-if="sortedComponents.length" class="detail-list">
          <div v-for="component in sortedComponents" :key="component.id" class="detail-row component-row">
            <div><strong>{{ component.name }}</strong><span class="num">{{ component.quantity }} × {{ component.unitPrice }} Kč = {{ component.totalPrice }} Kč</span></div>
            <div class="inline-actions"><button class="btn btn-ghost btn-compact" type="button" @click="$emit('editComponent', component)">Изменить</button><button class="btn btn-ghost btn-compact" type="button" @click="$emit('deleteComponent', component)">Удалить</button></div>
          </div>
        </div>
        <div v-else class="document-empty"><strong>Комплектация не указана</strong><span>Добавьте аккумулятор, замок, шлем или другое оснащение.</span></div>
      </div>

      <div class="detail-group">
        <div class="row-between"><div><h3>История аренды</h3><p class="admin-state-note">Периоды нельзя редактировать или удалять.</p></div><span class="meta">{{ rentals.length }}</span></div>
        <div v-if="rentals.length" class="rental-list">
          <article v-for="rental in rentals" :key="rental.id" class="rental-card">
            <div class="row-between rental-title"><div><strong>{{ courierName(rental.courierId) }}</strong><p class="num">{{ formatDate(rental.startedAt) }} — {{ formatDate(rental.endedAt) }}</p></div><span class="status" :class="rental.isActive ? 'status-warn' : 'status-ok'">{{ rental.isActive ? 'Активна' : 'Завершена' }}</span></div>
            <div class="rental-actions">
              <span v-if="rental.file" class="num">{{ rental.file.originalName }}</span><span v-else class="meta">Договор не приложен</span>
              <button v-if="rental.file" class="btn btn-secondary btn-compact" type="button" :disabled="downloadingFileIds.includes(rental.file.id)" @click="$emit('downloadContract', rental)">{{ downloadingFileIds.includes(rental.file.id) ? 'Скачиваем…' : 'Скачать договор' }}</button>
              <button v-else class="btn btn-secondary btn-compact" type="button" @click="$emit('attachContract', rental)">Приложить договор</button>
              <button v-if="rental.isActive" class="btn btn-ghost btn-compact" type="button" @click="$emit('closeRental', rental)">Завершить</button>
            </div>
          </article>
        </div>
        <div v-else-if="rentalLoading" class="document-empty"><span class="spinner" aria-hidden="true"></span><strong>Загружаем историю</strong></div>
        <div v-else class="document-empty"><strong>История пуста</strong><span>Первая выдача появится здесь.</span></div>
        <button v-if="rentalsNext" class="btn btn-secondary rental-more" type="button" :disabled="rentalLoading" @click="$emit('loadMoreRentals')">{{ rentalLoading ? 'Загружаем…' : 'Загрузить ещё' }}</button>
      </div>
      <p v-if="error" class="form-api-error" role="alert">{{ error }}</p>
    </div>
    <div class="modal-footer admin-detail-footer"><button class="btn btn-danger btn-danger-ghost" type="button" :disabled="busy" @click="$emit('delete')">Удалить велосипед</button><span class="modal-footer-spacer"></span><button class="btn btn-primary" type="button" :disabled="busy" @click="$emit('edit')">Редактировать</button></div>
  </AppModal>
</template>
