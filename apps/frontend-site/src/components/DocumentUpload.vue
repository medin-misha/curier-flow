<script setup lang="ts">
import { ref } from 'vue'
import { t, ui } from '../content/i18n'
const props = defineProps<{ label: string; files: File[]; error?: string; id: string; disabled: boolean }>()
const emit = defineEmits<{ change: [files: File[]] }>()
const input = ref<HTMLInputElement>()
const dragging = ref(false)
function add(files: FileList | null) { if (!props.disabled && files) emit('change', [...props.files, ...Array.from(files)]) }
function choose(event: Event) {
  const element = event.target as HTMLInputElement
  add(element.files)
  element.value = ''
}
function drop(event: DragEvent) { dragging.value = false; add(event.dataTransfer?.files ?? null) }
</script>

<template>
  <div class="upload-group">
    <div class="drop-zone" :class="{ dragging, 'field-invalid': error }"
      @dragover.prevent="dragging = !disabled" @dragleave.prevent="dragging = false" @drop.prevent="drop">
      <button :id="id" type="button" class="upload-trigger" :disabled="disabled"
        :aria-invalid="!!error" :aria-describedby="`${id}-hint${error ? ` ${id}-error` : ''}`" @click="input?.click()">
        <span class="drop-zone-label">{{ label }}</span>
        <span class="drop-zone-hint">{{ t('form.documents.drop_here') }}</span>
        <span :id="`${id}-hint`" class="field-hint">{{ ui('fileHint') }}</span>
      </button>
      <input ref="input" class="hidden-file-input" type="file" accept="image/png,image/jpeg,image/webp,application/pdf" multiple :aria-label="label" :disabled="disabled" @change="choose" />
      <ul v-if="files.length" class="file-list">
        <li v-for="(file, index) in files" :key="`${file.name}-${index}`" class="file-item">
          <span>{{ file.name }} · {{ Math.max(1, Math.ceil(file.size / 1024)) }} KB</span>
          <button type="button" class="remove-file" :disabled="disabled" :aria-label="`${ui('remove')}: ${file.name}`" @click="emit('change', files.filter((_, position) => position !== index))">×</button>
        </li>
      </ul>
    </div>
    <p v-if="error" :id="`${id}-error`" class="field-error-msg">{{ error }}</p>
  </div>
</template>
