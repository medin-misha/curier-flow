<script setup lang="ts">
import type { Courier } from '../../types/courier'

defineProps<{
  couriers: Courier[]
}>()

defineEmits<{
  select: [courier: Courier, event: MouseEvent]
}>()
</script>

<template>
  <div class="table-shell">
    <table v-if="couriers.length" class="ds-table" data-od-id="couriers-table">
      <thead>
        <tr>
          <th class="col-courier">Курьер</th>
          <th class="col-contact">Контакты</th>
          <th class="col-city">Город</th>
          <th class="col-platform">Платформы</th>
          <th class="col-docs">Документы</th>
          <th class="col-consent">Согласие</th>
          <th class="col-updated">Обновлено</th>
          <th class="col-action"><span class="visually-hidden">Действия</span></th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="courier in couriers"
          :key="courier.id"
          :data-od-id="`courier-row-${courier.id}`"
        >
          <td data-label="Курьер">
            <div class="person">
              <strong>{{ courier.fullName }}</strong>
              <span class="num">ID {{ courier.id }}</span>
            </div>
          </td>
          <td data-label="Контакты">
            <div class="contact-cell">
              <a :href="`mailto:${courier.email}`">{{ courier.email }}</a>
              <span class="num">{{ courier.phone }}</span>
            </div>
          </td>
          <td class="city-cell" data-label="Город">{{ courier.city || '—' }}</td>
          <td data-label="Платформы">
            <div v-if="courier.platforms.length" class="tag-list">
              <span v-for="platform in courier.platforms" :key="platform.name" class="tag">
                {{ platform.name }}
              </span>
            </div>
            <span v-else class="meta">Не подключены</span>
          </td>
          <td data-label="Документы">
            <span
              class="status"
              :class="courier.platforms[0]?.status === 'active' ? 'status-ok' : 'status-warn'"
            >
              {{ courier.documents }} · {{ courier.documentStatus }}
            </span>
          </td>
          <td data-label="Согласие">
            <span class="status" :class="courier.consent ? 'status-ok' : 'status-warn'">
              {{ courier.consent ? 'Получено' : 'Не получено' }}
            </span>
          </td>
          <td data-label="Обновлено"><span class="num">{{ courier.updated }}</span></td>
          <td data-label="Действия">
            <button
              class="table-action"
              type="button"
              :aria-label="`Открыть профиль ${courier.fullName}`"
              @click="$emit('select', courier, $event)"
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.8"
                aria-hidden="true"
              >
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
      <h2>Ничего не найдено</h2>
      <p>Проверьте точное имя, email или телефон и повторите поиск.</p>
    </div>
  </div>
</template>
