<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import AuthLoading from './components/auth/AuthLoading.vue'
import AdminsAdmin from './components/admins/AdminsAdmin.vue'
import BikesAdmin from './components/bikes/BikesAdmin.vue'
import LoginScreen from './components/auth/LoginScreen.vue'
import CourierAdmin from './components/couriers/CourierAdmin.vue'
import DocumentsAdmin from './components/documents/DocumentsAdmin.vue'
import FinanceAdmin from './components/finance/FinanceAdmin.vue'
import AdminHeader from './components/layout/AdminHeader.vue'
import { useAuthSession } from './composables/useAuthSession'

const auth = useAuthSession()
const activeTab = ref<'couriers' | 'bikes' | 'finance' | 'documents' | 'admins'>('couriers')
const financeBusy = ref(false)
const documentsBusy = ref(false)
const couriersBusy = ref(false)

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
      :navigation-locked="financeBusy || documentsBusy || couriersBusy"
      :active-tab="activeTab"
      @logout="auth.logout"
      @select-tab="activeTab = $event"
    />
    <CourierAdmin v-if="activeTab === 'couriers'" @busy-change="couriersBusy = $event" />
    <BikesAdmin v-else-if="activeTab === 'bikes'" />
    <FinanceAdmin v-else-if="activeTab === 'finance'" @busy-change="financeBusy = $event" />
    <DocumentsAdmin
      v-else-if="activeTab === 'documents'"
      @busy-change="documentsBusy = $event"
    />
    <AdminsAdmin
      v-else-if="activeTab === 'admins'"
      :current-admin-id="auth.admin.value.id"
      @current-admin-updated="auth.syncAdmin"
      @current-password-reset="auth.logout"
    />
  </template>
</template>
