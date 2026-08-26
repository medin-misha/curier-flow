<script setup lang="ts">
withDefaults(
  defineProps<{
    title: string
    message?: string
  }>(),
  {
    message: '',
  },
)
</script>

<template>
  <Teleport to="body">
    <div class="toast" role="status" aria-live="polite">
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="1.8"
        aria-hidden="true"
      >
        <path d="m5 12 4 4L19 6" />
      </svg>
      <div>
        <strong>{{ title }}</strong>
        <span v-if="message">{{ message }}</span>
      </div>
    </div>
  </Teleport>
</template>
