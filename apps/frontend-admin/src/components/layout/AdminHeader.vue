<script setup lang="ts">
import { computed } from 'vue'
import type { Admin } from '../../types/auth'

const props = defineProps<{
  admin: Admin
  loggingOut: boolean
}>()

defineEmits<{
  logout: []
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
        <button class="tab" type="button" aria-current="page" data-od-id="tab-couriers">
          Couriers
        </button>
      </nav>
      <button
        class="account account-button"
        type="button"
        data-od-id="account-menu"
        :disabled="loggingOut"
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
