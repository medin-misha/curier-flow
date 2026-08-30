<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { adminErrorMessage } from '../../api/admins'
import { useAdminsRegistry } from '../../composables/useAdminsRegistry'
import type { Admin, AdminCreateInput, AdminUpdateInput } from '../../types/admin'
import AppToast from '../ui/AppToast.vue'
import AdminCreateModal from './AdminCreateModal.vue'
import AdminDeactivateModal from './AdminDeactivateModal.vue'
import AdminDetailsModal from './AdminDetailsModal.vue'
import AdminEditModal from './AdminEditModal.vue'
import AdminPasswordModal from './AdminPasswordModal.vue'
import AdminsRegistry from './AdminsRegistry.vue'

const props = defineProps<{
  currentAdminId: string
}>()

const emit = defineEmits<{
  currentAdminUpdated: [admin: Admin]
  currentPasswordReset: []
}>()

const registry = useAdminsRegistry()
const selectedAdmin = ref<Admin | null>(null)
const createOpen = ref(false)
const editOpen = ref(false)
const passwordOpen = ref(false)
const deactivateOpen = ref(false)
const creating = ref(false)
const saving = ref(false)
const resettingPassword = ref(false)
const changingState = ref(false)
const createError = ref('')
const editError = ref('')
const passwordError = ref('')
const stateError = ref('')
const toastVisible = ref(false)
const toastTitle = ref('')
const toastMessage = ref('')
const lastFocused = ref<HTMLElement | null>(null)
let toastTimer: ReturnType<typeof setTimeout> | undefined
let detailsSequence = 0
let createSignature = ''
let createIdempotencyKey = ''

const paginationSummary = computed(
  () => `Страница ${registry.currentPage.value} · записей ${registry.admins.value.length}`,
)

watch([createOpen, editOpen, passwordOpen, deactivateOpen, selectedAdmin], () => {
  document.body.classList.toggle(
    'modal-open',
    createOpen.value ||
      editOpen.value ||
      passwordOpen.value ||
      deactivateOpen.value ||
      Boolean(selectedAdmin.value),
  )
})

function rememberFocus(trigger?: EventTarget | null) {
  lastFocused.value =
    trigger instanceof HTMLElement ? trigger : (document.activeElement as HTMLElement | null)
}

function restoreFocus() {
  void nextTick(() => lastFocused.value?.focus())
}

function showToast(title: string, message: string) {
  toastTitle.value = title
  toastMessage.value = message
  toastVisible.value = true
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => {
    toastVisible.value = false
  }, 4_200)
}

function openCreate(event: MouseEvent) {
  rememberFocus(event.currentTarget)
  createError.value = ''
  createSignature = ''
  createIdempotencyKey = ''
  createOpen.value = true
}

function closeCreate() {
  if (creating.value) return
  createOpen.value = false
  createSignature = ''
  createIdempotencyKey = ''
  restoreFocus()
}

async function submitCreate(input: AdminCreateInput) {
  const signature = JSON.stringify(input)
  if (signature !== createSignature) {
    createSignature = signature
    createIdempotencyKey = crypto.randomUUID()
  }
  creating.value = true
  createError.value = ''
  try {
    const created = await registry.create(input, createIdempotencyKey)
    createOpen.value = false
    createSignature = ''
    createIdempotencyKey = ''
    showToast('Администратор создан', `${created.username} добавлен в реестр.`)
    restoreFocus()
  } catch (error) {
    createError.value = adminErrorMessage(error, 'Не удалось создать администратора.')
  } finally {
    creating.value = false
  }
}

async function openDetails(admin: Admin, event: MouseEvent) {
  const sequence = ++detailsSequence
  rememberFocus(event.currentTarget)
  selectedAdmin.value = admin
  stateError.value = ''
  try {
    const fresh = await registry.retrieve(admin.id)
    if (sequence === detailsSequence && selectedAdmin.value?.id === fresh.id) {
      registry.replaceAdmin(fresh)
      selectedAdmin.value = fresh
    }
  } catch (error) {
    if (sequence !== detailsSequence) return
    showToast(
      'Карточка открыта из списка',
      adminErrorMessage(error, 'Не удалось обновить данные администратора.'),
    )
  }
}

function closeDetails() {
  if (changingState.value) return
  detailsSequence += 1
  selectedAdmin.value = null
  stateError.value = ''
  restoreFocus()
}

function openEdit() {
  detailsSequence += 1
  editError.value = ''
  editOpen.value = true
}

function closeEdit() {
  if (saving.value) return
  editOpen.value = false
}

async function submitEdit(input: AdminUpdateInput) {
  if (!selectedAdmin.value) return
  saving.value = true
  editError.value = ''
  try {
    const updated = await registry.update(selectedAdmin.value.id, input)
    selectedAdmin.value = updated
    editOpen.value = false
    if (updated.id === props.currentAdminId) emit('currentAdminUpdated', updated)
    showToast('Изменения сохранены', `Профиль ${updated.username} обновлён.`)
  } catch (error) {
    editError.value = adminErrorMessage(error, 'Не удалось сохранить изменения.')
  } finally {
    saving.value = false
  }
}

function openPassword() {
  detailsSequence += 1
  passwordError.value = ''
  passwordOpen.value = true
}

function closePassword() {
  if (resettingPassword.value) return
  passwordOpen.value = false
}

async function submitPassword(password: string) {
  if (!selectedAdmin.value) return
  resettingPassword.value = true
  passwordError.value = ''
  const admin = selectedAdmin.value
  try {
    await registry.resetPassword(admin.id, password)
    passwordOpen.value = false
    if (admin.id === props.currentAdminId) {
      emit('currentPasswordReset')
      return
    }
    const sequence = ++detailsSequence
    void registry
      .retrieve(admin.id)
      .then((fresh) => {
        if (sequence === detailsSequence && selectedAdmin.value?.id === fresh.id) {
          registry.replaceAdmin(fresh)
          selectedAdmin.value = fresh
        }
      })
      .catch(() => undefined)
    showToast('Пароль изменён', `Сессии ${admin.username} завершены.`)
  } catch (error) {
    passwordError.value = adminErrorMessage(error, 'Не удалось изменить пароль.')
  } finally {
    resettingPassword.value = false
  }
}

function openDeactivate() {
  detailsSequence += 1
  stateError.value = ''
  deactivateOpen.value = true
}

function closeDeactivate() {
  if (changingState.value) return
  deactivateOpen.value = false
}

async function confirmDeactivate() {
  if (!selectedAdmin.value) return
  changingState.value = true
  stateError.value = ''
  try {
    const updated = await registry.setActive(selectedAdmin.value.id, false)
    selectedAdmin.value = updated
    deactivateOpen.value = false
    showToast('Доступ отключён', `${updated.username} деактивирован.`)
  } catch (error) {
    stateError.value = adminErrorMessage(error, 'Не удалось деактивировать администратора.')
  } finally {
    changingState.value = false
  }
}

async function activate() {
  if (!selectedAdmin.value) return
  detailsSequence += 1
  changingState.value = true
  stateError.value = ''
  try {
    const updated = await registry.setActive(selectedAdmin.value.id, true)
    selectedAdmin.value = updated
    showToast('Доступ восстановлен', `${updated.username} снова активен.`)
  } catch (error) {
    stateError.value = adminErrorMessage(error, 'Не удалось активировать администратора.')
  } finally {
    changingState.value = false
  }
}

onMounted(() => {
  void registry.loadPage(1)
})

onBeforeUnmount(() => {
  document.body.classList.remove('modal-open')
  if (toastTimer) clearTimeout(toastTimer)
})
</script>

<template>
  <main id="content">
    <AdminsRegistry
      :admins="registry.admins.value"
      :current-admin-id="currentAdminId"
      :current-page="registry.currentPage.value"
      :pagination-summary="paginationSummary"
      :has-next="Boolean(registry.nextCursor.value)"
      :loading="registry.loading.value"
      :error="registry.loadError.value"
      @create="openCreate"
      @select="openDetails"
      @page="registry.pageTo"
      @retry="registry.loadPage(registry.currentPage.value)"
    />
  </main>

  <AdminCreateModal v-if="createOpen" :saving="creating" :error="createError" @close="closeCreate" @submit="submitCreate" />
  <AdminDetailsModal
    v-if="selectedAdmin && !editOpen && !passwordOpen && !deactivateOpen"
    :admin="selectedAdmin"
    :current-admin-id="currentAdminId"
    :changing-state="changingState"
    :action-error="stateError"
    @close="closeDetails"
    @edit="openEdit"
    @reset-password="openPassword"
    @activate="activate"
    @deactivate="openDeactivate"
  />
  <AdminEditModal v-if="selectedAdmin && editOpen" :admin="selectedAdmin" :saving="saving" :error="editError" @close="closeEdit" @save="submitEdit" />
  <AdminPasswordModal v-if="selectedAdmin && passwordOpen" :admin="selectedAdmin" :saving="resettingPassword" :error="passwordError" @close="closePassword" @save="submitPassword" />
  <AdminDeactivateModal v-if="selectedAdmin && deactivateOpen" :admin="selectedAdmin" :saving="changingState" :error="stateError" @close="closeDeactivate" @confirm="confirmDeactivate" />
  <AppToast v-if="toastVisible" :title="toastTitle" :message="toastMessage" />
</template>
