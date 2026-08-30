<script setup lang="ts">
import type { Admin } from '../../types/admin'

defineProps<{
  admins: Admin[]
  currentAdminId: string
}>()

defineEmits<{
  select: [admin: Admin, event: MouseEvent]
}>()

function formatDate(value: string) {
  return new Intl.DateTimeFormat('ru-RU').format(new Date(value))
}
</script>

<template>
  <div class="table-shell">
    <table v-if="admins.length" class="ds-table admins-table" data-od-id="admins-table">
      <thead>
        <tr>
          <th class="col-admin">Администратор</th>
          <th class="col-admin-telegram">Telegram ID</th>
          <th class="col-admin-status">Статус</th>
          <th class="col-admin-date">Создан</th>
          <th class="col-admin-date">Обновлён</th>
          <th class="col-action"><span class="visually-hidden">Действия</span></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="admin in admins" :key="admin.id" :data-od-id="`admin-row-${admin.id}`">
          <td data-label="Администратор">
            <div class="person">
              <strong>{{ admin.username }}</strong>
              <span class="num">ID {{ admin.id }}</span>
              <span v-if="admin.id === currentAdminId" class="tag admin-current-tag">Вы</span>
            </div>
          </td>
          <td data-label="Telegram ID">
            <span class="num">{{ admin.telegramId ?? 'Не указан' }}</span>
          </td>
          <td data-label="Статус">
            <span class="status" :class="admin.isActive ? 'status-ok' : 'status-warn'">
              {{ admin.isActive ? 'Активен' : 'Неактивен' }}
            </span>
          </td>
          <td data-label="Создан"><span class="num">{{ formatDate(admin.createdAt) }}</span></td>
          <td data-label="Обновлён"><span class="num">{{ formatDate(admin.updatedAt) }}</span></td>
          <td data-label="Действия">
            <button
              class="table-action"
              type="button"
              :aria-label="`Открыть профиль ${admin.username}`"
              :data-od-id="`open-admin-${admin.id}`"
              @click="$emit('select', admin, $event)"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                <circle cx="12" cy="5" r="1" />
                <circle cx="12" cy="12" r="1" />
                <circle cx="12" cy="19" r="1" />
              </svg>
            </button>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-else class="empty-state">
      <h2>Администраторов нет</h2>
      <p>Создайте учётную запись для доступа к операционной панели.</p>
    </div>
  </div>
</template>
