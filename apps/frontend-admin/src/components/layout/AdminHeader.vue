<script setup lang="ts">
import { computed } from 'vue'
import type { Admin } from '../../types/auth'

const props = defineProps<{
  admin: Admin
  loggingOut: boolean
  navigationLocked: boolean
  activeTab: 'couriers' | 'bikes' | 'finance' | 'documents' | 'admins'
}>()

defineEmits<{
  logout: []
  selectTab: [tab: 'couriers' | 'bikes' | 'finance' | 'documents' | 'admins']
}>()

const initials = computed(() => props.admin.username.slice(0, 2).toLocaleUpperCase('ru'))
</script>

<template>
  <header class="topnav" data-od-id="topnav">
    <div class="container topnav-inner">
      <a class="brand" href="#content" data-od-id="brand-home" aria-label="MFS — главная">
        <span class="brand-copy">
          <strong>May Fleet Solutions</strong>
          <span>Операционная панель</span>
        </span>
      </a>
      <nav class="tabs" aria-label="Разделы панели">
        <button
          class="tab"
          type="button"
          :disabled="navigationLocked"
          :aria-current="activeTab === 'couriers' ? 'page' : undefined"
          data-od-id="tab-couriers"
          @click="$emit('selectTab', 'couriers')"
        >
          <svg class="tab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
            <circle cx="9" cy="6" r="3" />
            <path d="M3 21v-3a6 6 0 0 1 9-5.2" />
            <rect x="14" y="13" width="7" height="8" rx="1.5" />
            <path d="M17.5 13v3" />
          </svg>
          Курьеры
        </button>
        <button
          class="tab"
          type="button"
          :disabled="navigationLocked"
          :aria-current="activeTab === 'bikes' ? 'page' : undefined"
          data-od-id="tab-bikes"
          @click="$emit('selectTab', 'bikes')"
        >
          <svg class="tab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
            <circle cx="5" cy="17" r="4" />
            <circle cx="19" cy="17" r="4" />
            <path d="m5 17 5-9 5 9H5m5-9h6M8 5h4m-2 0v3m9 9-4-13h3" />
          </svg>
          Велосипеды
        </button>
        <button
          class="tab"
          type="button"
          :disabled="navigationLocked"
          :aria-current="activeTab === 'finance' ? 'page' : undefined"
          data-od-id="tab-finance"
          @click="$emit('selectTab', 'finance')"
        >
          <svg class="tab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
            <path d="M20 8V6a2 2 0 0 0-2-2H6a3 3 0 0 0 0 6h13a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H6a3 3 0 0 1-3-3V7" />
            <path d="M21 13h-4a2 2 0 0 0 0 4h4" />
          </svg>
          Финансы
        </button>
        <button
          class="tab"
          type="button"
          :disabled="navigationLocked"
          :aria-current="activeTab === 'documents' ? 'page' : undefined"
          data-od-id="tab-documents"
          @click="$emit('selectTab', 'documents')"
        >
          <svg class="tab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
            <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9l-6-6Z" />
            <path d="M14 3v6h6M8 13h8m-8 4h5" />
          </svg>
          Документы
        </button>
        <button
          class="tab"
          type="button"
          :disabled="navigationLocked"
          :aria-current="activeTab === 'admins' ? 'page' : undefined"
          data-od-id="tab-admins"
          @click="$emit('selectTab', 'admins')"
        >
          <svg class="tab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
            <path d="m12 2 8 3v6c0 5-3.5 8.5-8 11-4.5-2.5-8-6-8-11V5l8-3Z" />
            <circle cx="12" cy="9" r="2.5" />
            <path d="M8 16a4 4 0 0 1 8 0" />
          </svg>
          Администраторы
        </button>
      </nav>
      <button
        class="account account-button"
        type="button"
        data-od-id="account-menu"
        :disabled="loggingOut || navigationLocked"
        aria-label="Выйти из панели"
        @click="$emit('logout')"
      >
        <div class="account-copy">
          <strong>{{ admin.username }}</strong>
          <span>{{ loggingOut ? 'Выходим…' : 'Выйти' }}</span>
        </div>
        <span class="avatar" aria-hidden="true">{{ initials }}</span>
      </button>
    </div>
  </header>
</template>
