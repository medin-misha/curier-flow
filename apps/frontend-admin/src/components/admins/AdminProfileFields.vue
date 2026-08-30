<script setup lang="ts">
import type { AdminProfileErrors, AdminProfileForm } from './adminForm'

withDefaults(
  defineProps<{
    form: AdminProfileForm
    errors: AdminProfileErrors
    idPrefix?: string
  }>(),
  { idPrefix: '' },
)

function fieldId(prefix: string, field: string) {
  return prefix ? `${prefix}-${field}` : field
}
</script>

<template>
  <div class="form-grid">
    <div class="field" :class="{ invalid: errors.username }">
      <label class="required" :for="fieldId(idPrefix, 'username')">Username</label>
      <input
        :id="fieldId(idPrefix, 'username')"
        v-model="form.username"
        class="input"
        type="text"
        autocomplete="off"
        maxlength="64"
        placeholder="admin.name"
        :aria-invalid="Boolean(errors.username)"
      />
      <span class="field-error" role="alert">{{ errors.username }}</span>
    </div>
    <div class="field" :class="{ invalid: errors.telegramId }">
      <label :for="fieldId(idPrefix, 'telegramId')">Telegram ID</label>
      <input
        :id="fieldId(idPrefix, 'telegramId')"
        v-model="form.telegramId"
        class="input num"
        type="text"
        inputmode="numeric"
        autocomplete="off"
        placeholder="Не указан"
        :aria-invalid="Boolean(errors.telegramId)"
      />
      <span class="field-error" role="alert">{{ errors.telegramId }}</span>
    </div>
  </div>
</template>
