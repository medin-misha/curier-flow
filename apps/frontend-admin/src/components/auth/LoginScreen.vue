<script setup lang="ts">
import { reactive } from 'vue'
import type { LoginCredentials } from '../../types/auth'

defineProps<{
  busy: boolean
  error: string
}>()

const emit = defineEmits<{
  login: [credentials: LoginCredentials]
}>()

const form = reactive({
  username: '',
  password: '',
})

function submit() {
  emit('login', {
    username: form.username.trim().toLocaleLowerCase('en'),
    password: form.password,
  })
}
</script>

<template>
  <main class="auth-shell">
    <section class="auth-panel" aria-labelledby="loginTitle">
      <div class="auth-brand">
        <span class="eyebrow">May Fleet Solutions</span>
        <h1 id="loginTitle">Вход в панель</h1>
        <p>Используйте административную учётную запись.</p>
      </div>

      <form class="auth-form" @submit.prevent="submit">
        <div class="field">
          <label class="required" for="username">Логин</label>
          <input
            id="username"
            v-model="form.username"
            class="input"
            name="username"
            autocomplete="username"
            pattern="[a-z0-9._-]{3,64}"
            minlength="3"
            maxlength="64"
            required
            autofocus
          />
        </div>
        <div class="field">
          <label class="required" for="password">Пароль</label>
          <input
            id="password"
            v-model="form.password"
            class="input"
            name="password"
            type="password"
            autocomplete="current-password"
            minlength="12"
            maxlength="128"
            required
          />
        </div>
        <p v-if="error" class="auth-error" role="alert">{{ error }}</p>
        <button class="btn btn-primary auth-submit" type="submit" :disabled="busy">
          {{ busy ? 'Входим…' : 'Войти' }}
        </button>
      </form>
    </section>
  </main>
</template>
