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
          Couriers
        </button>
        <button
          class="tab"
          type="button"
          :disabled="navigationLocked"
          :aria-current="activeTab === 'bikes' ? 'page' : undefined"
          data-od-id="tab-bikes"
          @click="$emit('selectTab', 'bikes')"
        >
          Bikes
        </button>
        <button
          class="tab"
          type="button"
          :disabled="navigationLocked"
          :aria-current="activeTab === 'finance' ? 'page' : undefined"
          data-od-id="tab-finance"
          @click="$emit('selectTab', 'finance')"
        >
          Finance
        </button>
        <button
          class="tab"
          type="button"
          :disabled="navigationLocked"
          :aria-current="activeTab === 'documents' ? 'page' : undefined"
          data-od-id="tab-documents"
          @click="$emit('selectTab', 'documents')"
        >
          Documents
        </button>
        <button
          class="tab"
          type="button"
          :disabled="navigationLocked"
          :aria-current="activeTab === 'admins' ? 'page' : undefined"
          data-od-id="tab-admins"
          @click="$emit('selectTab', 'admins')"
        >
          Admins
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
