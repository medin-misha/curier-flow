<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import AuthLoading from './components/auth/AuthLoading.vue'
import LoginScreen from './components/auth/LoginScreen.vue'
import CourierAdmin from './components/couriers/CourierAdmin.vue'
import AdminHeader from './components/layout/AdminHeader.vue'
import { useAuthSession } from './composables/useAuthSession'

const auth = useAuthSession()

onMounted(auth.initialize)
onBeforeUnmount(auth.dispose)
</script>

<template>
  <AuthLoading v-if="auth.status.value === 'checking'" />
  <LoginScreen
    v-else-if="auth.status.value === 'anonymous' || !auth.admin.value"
    :busy="auth.busy.value"
    :error="auth.error.value"
    @login="auth.login"
  />
  <template v-else>
    <AdminHeader
      :admin="auth.admin.value"
      :logging-out="auth.busy.value"
      @logout="auth.logout"
    />
    <CourierAdmin />
  </template>
</template>
