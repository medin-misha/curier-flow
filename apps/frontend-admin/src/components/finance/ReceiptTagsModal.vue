<script setup lang="ts">
import { ref } from 'vue'
import type { ReceiptTag } from '../../types/receipt'
import AppModal from '../ui/AppModal.vue'

defineProps<{
  tags: ReceiptTag[]
  busy: boolean
  error: string
}>()

const emit = defineEmits<{
  close: []
  create: [name: string]
  rename: [tagId: string, name: string]
  remove: [tagId: string]
}>()

const newName = ref('')
const editingId = ref<string | null>(null)
const editingName = ref('')
const deletingId = ref<string | null>(null)
const validationError = ref('')

function normalized(value: string) {
  return value.trim()
}

function create() {
  const name = normalized(newName.value)
  if (!name || name.length > 64) {
    validationError.value = 'Введите название длиной от 1 до 64 символов.'
    return
  }
  validationError.value = ''
  emit('create', name)
  newName.value = ''
}

function startEdit(tag: ReceiptTag) {
  deletingId.value = null
  editingId.value = tag.id
  editingName.value = tag.name
}

function rename() {
  const name = normalized(editingName.value)
  if (!editingId.value || !name || name.length > 64) {
    validationError.value = 'Введите название длиной от 1 до 64 символов.'
    return
  }
  validationError.value = ''
  emit('rename', editingId.value, name)
  editingId.value = null
}
</script>

<template>
  <AppModal label-id="receiptTagsTitle" data-od-id="receipt-tags-dialog" @close="$emit('close')">
    <div class="modal-header">
      <div class="row-between">
        <div>
          <p class="eyebrow">Finance</p>
          <h2 id="receiptTagsTitle">Теги расходов</h2>
          <p>Тег задаёт тип расхода и может использоваться в нескольких чеках.</p>
        </div>
        <button class="btn btn-ghost btn-icon" type="button" aria-label="Закрыть" :disabled="busy" @click="$emit('close')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
            <path d="m6 6 12 12M18 6 6 18" />
          </svg>
        </button>
      </div>
    </div>

    <div class="modal-body">
      <form class="receipt-tag-create" @submit.prevent="create">
        <label class="field">
          <span>Новый тег</span>
          <input v-model="newName" class="input" maxlength="64" placeholder="Например, топливо" :disabled="busy" />
        </label>
        <button class="btn btn-primary" type="submit" :disabled="busy">Добавить</button>
      </form>

      <p v-if="validationError || error" class="form-api-error" role="alert">{{ validationError || error }}</p>

      <div v-if="tags.length" class="receipt-tag-manager-list">
        <div v-for="tag in tags" :key="tag.id" class="receipt-tag-manager-row">
          <template v-if="editingId === tag.id">
            <input v-model="editingName" class="input" maxlength="64" :disabled="busy" @keyup.enter="rename" />
            <button class="btn btn-primary btn-compact" type="button" :disabled="busy" @click="rename">Сохранить</button>
            <button class="btn btn-ghost btn-compact" type="button" :disabled="busy" @click="editingId = null">Отмена</button>
          </template>
          <template v-else-if="deletingId === tag.id">
            <span>Снять «{{ tag.name }}» со всех чеков и удалить?</span>
            <button class="btn btn-danger btn-compact" type="button" :disabled="busy" @click="$emit('remove', tag.id)">Удалить</button>
            <button class="btn btn-ghost btn-compact" type="button" :disabled="busy" @click="deletingId = null">Отмена</button>
          </template>
          <template v-else>
            <span class="tag">{{ tag.name }}</span>
            <span class="modal-footer-spacer"></span>
            <button class="btn btn-secondary btn-compact" type="button" :disabled="busy" @click="startEdit(tag)">Изменить</button>
            <button class="btn btn-danger btn-danger-ghost btn-compact" type="button" :disabled="busy" @click="deletingId = tag.id">Удалить</button>
          </template>
        </div>
      </div>
      <p v-else class="admin-state-note">Тегов пока нет.</p>
    </div>
  </AppModal>
</template>
