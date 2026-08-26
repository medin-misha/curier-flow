<script setup lang="ts">
import type { CourierFormErrors, CourierFormValues } from '../../types/courier'

const props = withDefaults(
  defineProps<{
    form: CourierFormValues
    errors: CourierFormErrors
    idPrefix?: string
  }>(),
  {
    idPrefix: '',
  },
)

function fieldId(name: string) {
  return props.idPrefix ? `${props.idPrefix}-${name}` : name
}
</script>

<template>
  <div class="form-grid">
    <div class="field" :class="{ invalid: errors.fullName }">
      <label class="required" :for="fieldId('fullName')">Полное имя</label>
      <input
        :id="fieldId('fullName')"
        v-model="form.fullName"
        class="input"
        autocomplete="name"
        placeholder="Например, Анна Коваль"
        :aria-invalid="errors.fullName"
        :aria-describedby="fieldId('fullNameError')"
      />
      <span :id="fieldId('fullNameError')" class="field-error">
        Укажите имя курьера.
      </span>
    </div>
    <div class="field" :class="{ invalid: errors.birthDate }">
      <label class="required" :for="fieldId('birthDate')">Дата рождения</label>
      <input
        :id="fieldId('birthDate')"
        v-model="form.birthDate"
        class="input"
        type="date"
        :aria-invalid="errors.birthDate"
        :aria-describedby="fieldId('birthDateError')"
      />
      <span :id="fieldId('birthDateError')" class="field-error">
        Укажите дату рождения.
      </span>
    </div>
    <div class="field" :class="{ invalid: errors.email }">
      <label class="required" :for="fieldId('email')">Email</label>
      <input
        :id="fieldId('email')"
        v-model="form.email"
        class="input"
        type="email"
        autocomplete="email"
        placeholder="courier@example.com"
        :aria-invalid="errors.email"
        :aria-describedby="fieldId('emailError')"
      />
      <span :id="fieldId('emailError')" class="field-error">
        Введите корректный email.
      </span>
    </div>
    <div class="field" :class="{ invalid: errors.phone }">
      <label class="required" :for="fieldId('phone')">Телефон</label>
      <input
        :id="fieldId('phone')"
        v-model="form.phone"
        class="input"
        type="tel"
        autocomplete="tel"
        placeholder="+43 660 000 0000"
        :aria-invalid="errors.phone"
        :aria-describedby="fieldId('phoneError')"
      />
      <span :id="fieldId('phoneError')" class="field-error">
        Укажите номер телефона.
      </span>
    </div>
    <div class="field">
      <label :for="fieldId('city')">Город</label>
      <input
        :id="fieldId('city')"
        v-model="form.city"
        class="input"
        autocomplete="address-level2"
        placeholder="Например, Прага"
      />
    </div>
    <div class="field">
      <label :for="fieldId('citizenship')">Гражданство</label>
      <input
        :id="fieldId('citizenship')"
        v-model="form.citizenship"
        class="input"
        placeholder="Страна"
      />
    </div>
    <div class="field field-wide">
      <label :for="fieldId('address')">Адрес</label>
      <input
        :id="fieldId('address')"
        v-model="form.address"
        class="input"
        autocomplete="street-address"
        placeholder="Улица, дом, индекс"
      />
    </div>
    <div class="field">
      <label :for="fieldId('bankAccount')">Банковский счёт</label>
      <input
        :id="fieldId('bankAccount')"
        v-model="form.bankAccount"
        class="input num"
        placeholder="CZ00 0000 0000 0000 0000 0000"
      />
    </div>
    <div class="field">
      <label :for="fieldId('source')">Источник</label>
      <select :id="fieldId('source')" v-model="form.source" class="select">
        <option value="">Не указан</option>
        <option>Рекомендация</option>
        <option>Сайт MFS</option>
        <option>Партнёр</option>
        <option>Реклама</option>
      </select>
    </div>
    <div class="field">
      <label :for="fieldId('contactPlatform')">Канал связи</label>
      <select
        :id="fieldId('contactPlatform')"
        v-model="form.contactPlatform"
        class="select"
      >
        <option value="">Не выбран</option>
        <option>Telegram</option>
        <option>WhatsApp</option>
        <option>Signal</option>
      </select>
    </div>
    <div class="field">
      <label :for="fieldId('contact')">Контакт в мессенджере</label>
      <input
        :id="fieldId('contact')"
        v-model="form.contact"
        class="input"
        placeholder="@username или номер"
      />
    </div>
    <label class="checkbox-row field-wide">
      <input v-model="form.consent" type="checkbox" />
      <span class="checkbox-copy">
        <strong>Получено согласие на обработку данных</strong>
        <span>Backend синхронизирует дату согласия при сохранении.</span>
      </span>
    </label>
  </div>
</template>
