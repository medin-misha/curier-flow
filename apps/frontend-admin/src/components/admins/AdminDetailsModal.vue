<script setup lang="ts">
import { computed } from 'vue'
import type { Admin } from '../../types/admin'
import AppModal from '../ui/AppModal.vue'

const props = defineProps<{
  admin: Admin
  currentAdminId: string
  changingState: boolean
  actionError: string
}>()

defineEmits<{
  close: []
  edit: []
  resetPassword: []
  activate: []
  deactivate: []
}>()

const isCurrent = computed(() => props.admin.id === props.currentAdminId)

function formatDate(value: string) {
  return new Intl.DateTimeFormat('ru-RU', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}
</script>

<template>
  <AppModal
    label-id="adminDetailTitle"
    modal-class="modal-detail"
    data-od-id="admin-detail-dialog"
    @close="$emit('close')"
  >
    <div class="modal-header">
      <div class="row-between">
        <div>
          <p class="eyebrow">Профиль администратора</p>
          <h2 id="adminDetailTitle">{{ admin.username }}</h2>
          <p class="num">ID {{ admin.id }}</p>
        </div>
        <button
          class="btn btn-ghost btn-icon"
          type="button"
          aria-label="Закрыть"
          :disabled="changingState"
          @click="$emit('close')"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
            <path d="m6 6 12 12M18 6 6 18" />
          </svg>
        </button>
      </div>
    </div>

    <div class="modal-body">
      <div class="detail-grid">
        <div class="detail-item">
          <span>Username</span>
          <strong>{{ admin.username }}</strong>
        </div>
        <div class="detail-item">
          <span>Telegram ID</span>
          <strong class="num">{{ admin.telegramId ?? 'Не указан' }}</strong>
        </div>
        <div class="detail-item">
          <span>Статус</span>
          <strong>{{ admin.isActive ? 'Активен' : 'Неактивен' }}</strong>
        </div>
        <div class="detail-item">
          <span>Текущая запись</span>
          <strong>{{ isCurrent ? 'Да' : 'Нет' }}</strong>
        </div>
        <div class="detail-item">
          <span>Создан</span>
          <strong class="num">{{ formatDate(admin.createdAt) }}</strong>
        </div>
        <div class="detail-item">
          <span>Обновлён</span>
          <strong class="num">{{ formatDate(admin.updatedAt) }}</strong>
        </div>
      </div>

      <div class="detail-group">
        <h3>Доступ к панели</h3>
        <p v-if="isCurrent && admin.isActive" class="admin-state-note">
          Собственную учётную запись нельзя деактивировать.
        </p>
        <p v-else-if="admin.isActive" class="admin-state-note">
          Деактивация завершит refresh-сессии администратора, но сохранит его профиль.
        </p>
        <p v-else class="admin-state-note">
          Неактивный администратор не может войти в панель. Профиль можно активировать повторно.
        </p>
      </div>
      <p v-if="actionError" class="form-api-error" role="alert">{{ actionError }}</p>
    </div>

    <div class="modal-footer admin-detail-footer">
      <button
        v-if="admin.isActive"
        class="btn btn-danger btn-danger-ghost"
        type="button"
        :disabled="isCurrent || changingState"
        :title="isCurrent ? 'Собственную учётную запись нельзя деактивировать' : undefined"
        @click="$emit('deactivate')"
      >
        {{ isCurrent ? 'Текущая запись' : 'Деактивировать' }}
      </button>
      <button
        v-else
        class="btn btn-secondary"
        type="button"
        :disabled="changingState"
        @click="$emit('activate')"
      >
        {{ changingState ? 'Активируем…' : 'Активировать' }}
      </button>
      <span class="modal-footer-spacer"></span>
      <button class="btn btn-secondary" type="button" :disabled="changingState" @click="$emit('resetPassword')">
        Сменить пароль
      </button>
      <button class="btn btn-primary" type="button" :disabled="changingState" @click="$emit('edit')">
        Редактировать
      </button>
    </div>
  </AppModal>
</template>
