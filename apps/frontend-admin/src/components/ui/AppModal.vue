<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'

withDefaults(
  defineProps<{
    labelId: string
    modalClass?: string
    dataOdId?: string
  }>(),
  {
    modalClass: '',
    dataOdId: undefined,
  },
)

const emit = defineEmits<{
  close: []
}>()

const layer = ref<HTMLDivElement | null>(null)

onMounted(async () => {
  await nextTick()
  layer.value
    ?.querySelector<HTMLElement>(
      'input:not([disabled]), button:not([disabled]), select:not([disabled])',
    )
    ?.focus()
})

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    emit('close')
    return
  }
  if (event.key !== 'Tab') return

  const focusable = Array.from(
    layer.value?.querySelectorAll<HTMLElement>(
      'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href]',
    ) ?? [],
  )
  if (!focusable.length) return

  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}
</script>

<template>
  <Teleport to="body">
    <div
      ref="layer"
      class="modal-layer"
      @mousedown.self="$emit('close')"
      @keydown="onKeydown"
    >
      <div
        class="modal"
        :class="modalClass"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="labelId"
        :data-od-id="dataOdId"
      >
        <slot />
      </div>
    </div>
  </Teleport>
</template>
