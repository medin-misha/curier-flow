<script setup lang="ts">
import AppModal from '../ui/AppModal.vue'

defineProps<{ title: string; message: string; action: string; saving: boolean; error: string }>()
defineEmits<{ close: []; confirm: [] }>()
</script>

<template>
  <AppModal label-id="confirmActionTitle" modal-class="modal-confirm" data-od-id="confirm-action-dialog" @close="$emit('close')">
    <div class="modal-header"><div class="row-between"><div><p class="eyebrow">Необратимое действие</p><h2 id="confirmActionTitle">{{ title }}</h2></div><button class="btn btn-ghost btn-icon" type="button" aria-label="Закрыть" :disabled="saving" @click="$emit('close')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg></button></div></div>
    <div class="modal-body"><p>{{ message }}</p><p v-if="error" class="form-api-error" role="alert">{{ error }}</p></div>
    <div class="modal-footer"><button class="btn btn-secondary" type="button" :disabled="saving" @click="$emit('close')">Отмена</button><button class="btn btn-danger" type="button" :disabled="saving" @click="$emit('confirm')">{{ saving ? 'Выполняем…' : action }}</button></div>
  </AppModal>
</template>
