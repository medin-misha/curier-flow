<script setup lang="ts">
import { nextTick, reactive, ref } from 'vue'
import type { Courier, CourierDocument, PlatformStatus } from '../../types/courier'
import AppModal from '../ui/AppModal.vue'

const MAX_FILE_SIZE = 10 * 1024 * 1024
const ALLOWED_FILE_TYPES = new Set(['application/pdf', 'image/jpeg', 'image/png'])

const emit = defineEmits<{
  close: []
  created: [courier: Courier]
}>()

function initialForm() {
  return {
    fullName: '',
    birthDate: '',
    email: '',
    phone: '',
    city: '',
    citizenship: '',
    address: '',
    bankAccount: '',
    source: '',
    contactPlatform: '',
    contact: '',
    consent: false,
    platform: '',
    platformStatus: 'review' as PlatformStatus,
  }
}

const form = reactive(initialForm())
const formErrors = reactive({
  fullName: false,
  birthDate: false,
  email: false,
  phone: false,
})
const selectedFile = ref<File | null>(null)
const fileError = ref('')

function onFileChange(event: Event) {
  const input = event.currentTarget as HTMLInputElement
  const file = input.files?.[0] ?? null
  fileError.value = ''

  if (file && !ALLOWED_FILE_TYPES.has(file.type)) {
    fileError.value = 'Выберите PDF, JPG или PNG.'
    input.value = ''
    selectedFile.value = null
    return
  }
  if (file && file.size > MAX_FILE_SIZE) {
    fileError.value = 'Размер файла не должен превышать 10 МБ.'
    input.value = ''
    selectedFile.value = null
    return
  }
  selectedFile.value = file
}

function validateForm() {
  formErrors.fullName = form.fullName.trim() === ''
  formErrors.birthDate = form.birthDate === ''
  formErrors.email = !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())
  formErrors.phone = form.phone.trim() === ''

  const firstError = (Object.keys(formErrors) as Array<keyof typeof formErrors>).find(
    (field) => formErrors[field],
  )
  if (firstError) {
    void nextTick(() => document.getElementById(firstError)?.focus())
    return false
  }
  return !fileError.value
}

function submitCourier() {
  if (!validateForm()) return

  const courierId = crypto.randomUUID().slice(0, 8)
  const createdAt = new Date().toISOString()
  let uploadedDocument: CourierDocument | null = null

  if (selectedFile.value) {
    const previewUrl = URL.createObjectURL(selectedFile.value)
    uploadedDocument = {
      id: `${courierId}-doc-01`,
      typeLabel: 'Документ курьера',
      purposeLabel: 'Онбординг',
      reviewStatus: 'processing',
      file: {
        id: `${courierId}-file-01`,
        originalName: selectedFile.value.name,
        contentType: selectedFile.value.type,
        size: selectedFile.value.size,
        status: 'AVAILABLE',
        ownerId: courierId,
        createdAt,
        previewUrl,
      },
      createdAt,
      updatedAt: createdAt,
    }
  }

  emit('created', {
    id: courierId,
    fullName: form.fullName.trim(),
    email: form.email.trim(),
    phone: form.phone.trim(),
    birthDate: form.birthDate,
    city: form.city || null,
    address: form.address.trim() || null,
    citizenship: form.citizenship.trim() || null,
    bank: form.bankAccount.trim() || null,
    contactPlatform: form.contactPlatform || null,
    contact: form.contact.trim() || null,
    source: form.source || null,
    consent: form.consent,
    platforms: form.platform
      ? [{ name: form.platform, status: form.platformStatus }]
      : [],
    documents: uploadedDocument ? 1 : 0,
    documentFiles: uploadedDocument ? [uploadedDocument] : [],
    documentStatus: uploadedDocument ? 'На проверке' : 'Нет документов',
    updated: new Intl.DateTimeFormat('ru-RU').format(new Date()),
  })
}
</script>

<template>
  <AppModal
    label-id="createTitle"
    data-od-id="create-courier-dialog"
    @close="$emit('close')"
  >
    <div class="modal-header">
      <div class="row-between">
        <div>
          <h2 id="createTitle">Новый курьер</h2>
          <p>Заполните профиль. Платформу и документ можно добавить сразу или позже.</p>
        </div>
        <button
          class="btn btn-ghost btn-icon"
          type="button"
          aria-label="Закрыть"
          @click="$emit('close')"
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            aria-hidden="true"
          >
            <path d="m6 6 12 12M18 6 6 18" />
          </svg>
        </button>
      </div>
    </div>

    <form novalidate @submit.prevent="submitCourier">
      <div class="modal-body">
        <div class="form-section">
          <div class="form-section-title">
            <h3>Основные данные</h3>
            <p>Поля с отметкой обязательны для создания профиля.</p>
          </div>
          <div class="form-grid">
            <div class="field" :class="{ invalid: formErrors.fullName }">
              <label class="required" for="fullName">Полное имя</label>
              <input
                id="fullName"
                v-model="form.fullName"
                class="input"
                autocomplete="name"
                placeholder="Например, Анна Коваль"
                :aria-invalid="formErrors.fullName"
                aria-describedby="fullNameError"
              />
              <span id="fullNameError" class="field-error">Укажите имя курьера.</span>
            </div>
            <div class="field" :class="{ invalid: formErrors.birthDate }">
              <label class="required" for="birthDate">Дата рождения</label>
              <input
                id="birthDate"
                v-model="form.birthDate"
                class="input"
                type="date"
                :aria-invalid="formErrors.birthDate"
                aria-describedby="birthDateError"
              />
              <span id="birthDateError" class="field-error">Укажите дату рождения.</span>
            </div>
            <div class="field" :class="{ invalid: formErrors.email }">
              <label class="required" for="email">Email</label>
              <input
                id="email"
                v-model="form.email"
                class="input"
                type="email"
                autocomplete="email"
                placeholder="courier@example.com"
                :aria-invalid="formErrors.email"
                aria-describedby="emailError"
              />
              <span id="emailError" class="field-error">Введите корректный email.</span>
            </div>
            <div class="field" :class="{ invalid: formErrors.phone }">
              <label class="required" for="phone">Телефон</label>
              <input
                id="phone"
                v-model="form.phone"
                class="input"
                type="tel"
                autocomplete="tel"
                placeholder="+43 660 000 0000"
                :aria-invalid="formErrors.phone"
                aria-describedby="phoneError"
              />
              <span id="phoneError" class="field-error">Укажите номер телефона.</span>
            </div>
            <div class="field">
              <label for="city">Город</label>
              <select id="city" v-model="form.city" class="select">
                <option value="">Не выбран</option>
                <option>Вена</option>
                <option>Грац</option>
                <option>Линц</option>
                <option>Зальцбург</option>
              </select>
            </div>
            <div class="field">
              <label for="citizenship">Гражданство</label>
              <input
                id="citizenship"
                v-model="form.citizenship"
                class="input"
                placeholder="Страна"
              />
            </div>
            <div class="field field-wide">
              <label for="address">Адрес</label>
              <input
                id="address"
                v-model="form.address"
                class="input"
                autocomplete="street-address"
                placeholder="Улица, дом, индекс"
              />
            </div>
            <div class="field">
              <label for="bankAccount">Банковский счёт</label>
              <input
                id="bankAccount"
                v-model="form.bankAccount"
                class="input num"
                placeholder="AT00 0000 0000 0000 0000"
              />
            </div>
            <div class="field">
              <label for="source">Источник</label>
              <select id="source" v-model="form.source" class="select">
                <option value="">Не указан</option>
                <option>Рекомендация</option>
                <option>Сайт MFS</option>
                <option>Партнёр</option>
                <option>Реклама</option>
              </select>
            </div>
            <div class="field">
              <label for="contactPlatform">Канал связи</label>
              <select id="contactPlatform" v-model="form.contactPlatform" class="select">
                <option value="">Не выбран</option>
                <option>Telegram</option>
                <option>WhatsApp</option>
                <option>Signal</option>
              </select>
            </div>
            <div class="field">
              <label for="contact">Контакт в мессенджере</label>
              <input
                id="contact"
                v-model="form.contact"
                class="input"
                placeholder="@username или номер"
              />
            </div>
            <label class="checkbox-row field-wide">
              <input v-model="form.consent" type="checkbox" />
              <span class="checkbox-copy">
                <strong>Получено согласие на обработку данных</strong>
                <span>Дата согласия будет зафиксирована в момент создания.</span>
              </span>
            </label>
          </div>
        </div>

        <div class="form-section">
          <div class="form-section-title">
            <h3>Регистрация на платформе</h3>
            <p>Необязательно. Дополнительные аккаунты можно подключить из профиля.</p>
          </div>
          <div class="form-grid">
            <div class="field">
              <label for="platform">Платформа доставки</label>
              <select id="platform" v-model="form.platform" class="select">
                <option value="">Без платформы</option>
                <option>Wolt</option>
                <option>Lieferando</option>
                <option>Bolt Food</option>
              </select>
            </div>
            <div class="field">
              <label for="platformStatus">Статус аккаунта</label>
              <select id="platformStatus" v-model="form.platformStatus" class="select">
                <option value="review">На проверке</option>
                <option value="active">Активен</option>
                <option value="blocked">Заблокирован</option>
              </select>
            </div>
          </div>
        </div>

        <div class="form-section">
          <div class="form-section-title">
            <h3>Первый документ</h3>
            <p>Файл сохраняется только в текущей сессии до подключения API.</p>
          </div>
          <div class="file-control" :class="{ invalid: fileError }">
            <div class="file-copy">
              <strong>Документ курьера</strong>
              <span>PDF, JPG или PNG · до 10 МБ</span>
              <span v-if="fileError" class="file-error" role="alert">{{ fileError }}</span>
            </div>
            <input type="file" accept=".pdf,.jpg,.jpeg,.png" @change="onFileChange" />
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" type="button" @click="$emit('close')">
          Отмена
        </button>
        <button class="btn btn-primary" type="submit" data-od-id="submit-courier">
          Создать курьера
        </button>
      </div>
    </form>
  </AppModal>
</template>
