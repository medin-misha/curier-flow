<script setup lang="ts">
import { ref } from 'vue'
import type { TransportRental } from '../../types/transport'
import AppModal from '../ui/AppModal.vue'

defineProps<{ rental: TransportRental; saving: boolean; error: string }>()
const emit = defineEmits<{ close: []; save: [file: File] }>()
const file = ref<File | null>(null)
const fileError = ref('')
const allowed = new Set(['application/pdf', 'image/jpeg', 'image/png', 'image/webp'])
const maxSize = 25 * 1024 * 1024

function selectFile(event: Event) {
  const input = event.currentTarget as HTMLInputElement
  const selected = input.files?.[0] ?? null
  fileError.value = ''
  if (selected && (!allowed.has(selected.type) || selected.size <= 0 || selected.size > maxSize)) {
    fileError.value = 'Выберите PDF, JPG, PNG или WebP размером до 25 МБ.'
    input.value = ''
    file.value = null
    return
  }
  file.value = selected
}
</script>

<template>
  <AppModal label-id="contractAttachTitle" modal-class="modal-confirm" data-od-id="contract-attach-dialog" @close="$emit('close')">
    <div class="modal-header"><div class="row-between"><div><h2 id="contractAttachTitle">Подписанный договор</h2><p>Файл нельзя будет заменить или отвязать</p></div><button class="btn btn-ghost btn-icon" type="button" aria-label="Закрыть" :disabled="saving" @click="$emit('close')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg></button></div></div>
    <div class="modal-body"><div class="file-control" :class="{ invalid: fileError }"><div class="file-copy"><strong>{{ file?.name || 'Договор аренды' }}</strong><span>PDF, JPG, PNG или WebP · до 25 МБ</span><span v-if="fileError" class="file-error" role="alert">{{ fileError }}</span></div><input type="file" accept=".pdf,.jpg,.jpeg,.png,.webp" :disabled="saving" @change="selectFile" /></div><p class="admin-state-note">Аренда {{ rental.id }}</p><p v-if="error" class="form-api-error" role="alert">{{ error }}</p></div>
    <div class="modal-footer"><button class="btn btn-secondary" type="button" :disabled="saving" @click="$emit('close')">Отмена</button><button class="btn btn-primary" type="button" :disabled="saving || !file" @click="file && $emit('save', file)">{{ saving ? 'Загружаем…' : 'Загрузить и приложить' }}</button></div>
  </AppModal>
</template>
