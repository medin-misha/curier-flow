<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listCouriers } from '../../api/couriers'
import type { Courier } from '../../types/courier'

const selectedId = defineModel<string>({ required: true })
const query = ref('')
const options = ref<Courier[]>([])
const loading = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const result = await listCouriers({ cursor: null, limit: 50, query: query.value })
    options.value = result.items
    if (selectedId.value && !options.value.some((courier) => courier.id === selectedId.value)) {
      options.value.unshift({ id: selectedId.value, fullName: selectedId.value } as Courier)
    }
  } catch {
    error.value = 'Не удалось загрузить курьеров.'
  } finally {
    loading.value = false
  }
}

onMounted(() => void load())
</script>

<template>
  <div class="courier-picker">
    <div class="courier-picker-search"><input v-model="query" class="input" type="search" placeholder="Точное имя, email или телефон" aria-label="Поиск курьера" @keydown.enter.prevent="load" /><button class="btn btn-secondary" type="button" :disabled="loading" @click="load">Найти</button></div>
    <select v-model="selectedId" class="select" :disabled="loading" aria-label="Курьер"><option value="">Выберите курьера</option><option v-for="courier in options" :key="courier.id" :value="courier.id">{{ courier.fullName }} · {{ courier.email || courier.id }}</option></select>
    <span v-if="error" class="field-error courier-picker-error" role="alert">{{ error }}</span>
  </div>
</template>
