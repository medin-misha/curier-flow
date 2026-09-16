<script setup lang="ts">
import { computed, nextTick, onUnmounted, reactive, ref, watch } from 'vue'
import { t, ui, type CopyKey } from '../content/i18n'
import DocumentUpload from './DocumentUpload.vue'
import { initialApplication, submitApplication, validateApplication, type Documents, type Errors, type Field } from '../features/application/application'

const emit = defineEmits<{ submitted: [outcome: 'created' | 'existing'] }>()
const form = reactive(initialApplication())
const documents = reactive<Documents>({ identity: [], residence: [] })
const errors = ref<Errors>({})
const attempted = ref(false)
const pending = ref(false)
const serverError = ref<CopyKey>()
const errorSummary = ref<HTMLDivElement>()
const czech = computed(() => form.citizenship === 'cz')
let active = true

watch(() => form.platform, value => {
  if (value) document.documentElement.dataset.platform = 'bolt'
  else delete document.documentElement.dataset.platform
})
watch(czech, () => { documents.identity = []; documents.residence = [] })
watch([form, documents], () => { if (attempted.value) errors.value = validateApplication(form, documents) }, { deep: true })
onUnmounted(() => { active = false; delete document.documentElement.dataset.platform })

const fields = [
  { key: 'fullName', label: 'name', type: 'text', autocomplete: 'name', placeholder: 'Ivan Ivanush', max: 255 },
  { key: 'city', label: 'city', type: 'text', autocomplete: 'address-level2', placeholder: '', max: 128 },
  { key: 'phone', label: 'phone', type: 'tel', autocomplete: 'tel', placeholder: '+420 777 123 456', max: 20 },
  { key: 'email', label: 'email', type: 'email', autocomplete: 'email', placeholder: 'ivan@example.com', max: 320 },
  { key: 'birthDate', label: 'birth_date', type: 'date', autocomplete: 'bday', placeholder: '', max: 10 },
  { key: 'address', label: 'address', type: 'text', autocomplete: 'street-address', placeholder: '', max: 528 },
] as const
const today = new Date().toLocaleDateString('sv-SE')
const countries = [{ value: 'cz', label: 'czech' }, { value: 'ua', label: 'ukraine' }, { value: 'tr', label: 'turkey' }, { value: 'ind', label: 'india' }, { value: 'sk', label: 'slovakia' }] as const
const message = (field: Field) => errors.value[field] ? ui(errors.value[field]!) : undefined

async function submit() {
  if (pending.value) return
  attempted.value = true
  serverError.value = undefined
  errors.value = validateApplication(form, documents)
  if (Object.keys(errors.value).length) {
    await nextTick()
    document.querySelector<HTMLElement>('.form-container [aria-invalid="true"]')?.focus()
    return
  }
  pending.value = true
  const result = await submitApplication(form, documents)
  if (!active) return
  pending.value = false
  if (result.ok) emit('submitted', result.outcome)
  else {
    serverError.value = result.error
    await nextTick()
    errorSummary.value?.focus()
  }
}
</script>

<template>
  <div class="form-page">
    <form class="form-container" novalidate :aria-busy="pending" @submit.prevent="submit">
      <div class="form-header">
        <h1>{{ t('form.header') }}</h1>
        <img v-if="form.platform" class="bolt-logo" src="/assets/bolt.png" alt="Bolt Food" />
      </div>
      <div class="field-group">
        <label id="platform-label">{{ t('form.work_in.label') }}</label>
        <p class="field-hint">{{ t('form.work_in.hint') }}</p>
        <div class="platform-picker" role="radiogroup" aria-labelledby="platform-label">
          <button type="button" class="platform-card bolt" :class="{ selected: form.platform }" role="radio"
            :aria-checked="!!form.platform" :aria-invalid="!!errors.platform" :aria-describedby="errors.platform ? 'platform-error' : undefined"
            :disabled="pending" @click="form.platform = 'bolt_food'">
            <span class="platform-swatch bolt-swatch">B</span>
            <span class="platform-info"><span class="platform-name">Bolt Food</span><span class="platform-tag">{{ t('form.work_in.bolt_tag') }}</span></span>
            <span class="platform-check"><span v-if="form.platform">✓</span></span>
          </button>
        </div>
        <p v-if="errors.platform" id="platform-error" class="field-error-msg">{{ message('platform') }}</p>
      </div>
      <div class="section-title"><span class="section-number">1.</span><span class="section-text">{{ t('form.section1.title') }}</span></div>
      <div v-for="field in fields" :key="field.key" class="field-group">
        <label :for="field.key">{{ t(`form.fields.${field.label}`) }}</label>
        <input :id="field.key" v-model="form[field.key]" :name="field.key" :type="field.type" :autocomplete="field.autocomplete" :placeholder="field.placeholder"
          :maxlength="field.max" :max="field.type === 'date' ? today : undefined" :disabled="pending" required
          :class="{ 'field-invalid': errors[field.key] }" :aria-invalid="!!errors[field.key]" :aria-describedby="errors[field.key] ? `${field.key}-error` : undefined" />
        <p v-if="errors[field.key]" :id="`${field.key}-error`" class="field-error-msg">{{ message(field.key) }}</p>
      </div>
      <div class="platform-section">
        <p id="contact-platform-label" class="platform-label">{{ t('form.platform.label') }}</p>
        <div class="checkbox-group" role="radiogroup" aria-labelledby="contact-platform-label" :aria-invalid="!!errors.contactPlatform">
          <label v-for="platform in (['telegram', 'whatsapp'] as const)" :key="platform" class="checkbox-item">
            <input v-model="form.contactPlatform" type="radio" name="contactPlatform" :value="platform" :disabled="pending" :aria-invalid="!!errors.contactPlatform" />
            <span>{{ platform === 'telegram' ? 'Telegram' : 'WhatsApp' }}</span>
          </label>
        </div>
        <p v-if="errors.contactPlatform" class="field-error-msg">{{ message('contactPlatform') }}</p>
        <p v-if="form.contactPlatform === 'whatsapp'" class="whatsapp-hint">{{ t('form.whatsapp-hint') }}</p>
        <div class="field-group">
          <label class="sr-only" for="contact">{{ ui('contactLabel') }}</label>
          <input id="contact" v-model="form.contact" :type="form.contactPlatform === 'whatsapp' ? 'tel' : 'text'" :placeholder="form.contactPlatform === 'telegram' ? '@username' : '+420…'"
            :disabled="pending || !form.contactPlatform" maxlength="255" required :class="{ 'field-invalid': errors.contact }"
            :aria-invalid="!!errors.contact" :aria-describedby="errors.contact ? 'contact-error' : undefined" />
          <p v-if="errors.contact" id="contact-error" class="field-error-msg">{{ message('contact') }}</p>
        </div>
      </div>
      <div class="field-group">
        <label for="bankAccount">{{ t('form.fields.invoice') }}</label>
        <input id="bankAccount" v-model="form.bankAccount" type="text" placeholder="1234567890/1234" maxlength="64" :disabled="pending" required
          :class="{ 'field-invalid': errors.bankAccount }" :aria-invalid="!!errors.bankAccount" :aria-describedby="errors.bankAccount ? 'bankAccount-error' : undefined" />
        <p v-if="errors.bankAccount" id="bankAccount-error" class="field-error-msg">{{ message('bankAccount') }}</p>
      </div>
      <div class="field-group">
        <label for="citizenship">{{ t('form.fields.citizenship') }}</label>
        <select id="citizenship" v-model="form.citizenship" :disabled="pending" required :class="{ 'field-invalid': errors.citizenship }" :aria-invalid="!!errors.citizenship" :aria-describedby="errors.citizenship ? 'citizenship-error' : undefined">
          <option disabled value="">{{ t('form.placeholders.citizenship') }}</option>
          <option v-for="country in countries" :key="country.value" :value="country.value">{{ ui(country.label) }}</option>
          <option value="other">{{ t('form.citizenship.other') }}</option>
        </select>
        <p v-if="errors.citizenship" id="citizenship-error" class="field-error-msg">{{ message('citizenship') }}</p>
      </div>
      <div class="field-group">
        <label for="source">{{ t('form.fields.how_found_it') }}</label>
        <input id="source" v-model="form.source" type="text" maxlength="64" :disabled="pending" required :class="{ 'field-invalid': errors.source }" :aria-invalid="!!errors.source" :aria-describedby="errors.source ? 'source-error' : undefined" />
        <p v-if="errors.source" id="source-error" class="field-error-msg">{{ message('source') }}</p>
      </div>
      <div class="section-title"><span class="section-number">2.</span><span class="section-text">{{ t('form.section2.title') }}</span></div>
      <DocumentUpload id="identity" :label="ui(czech ? 'idFront' : 'passport')" :files="documents.identity" :error="message('identity')" :disabled="pending" @change="documents.identity = $event" />
      <DocumentUpload id="residence" :label="ui(czech ? 'idBack' : 'residence')" :files="documents.residence" :error="message('residence')" :disabled="pending" @change="documents.residence = $event" />
      <div v-if="serverError" ref="errorSummary" class="form-error-banner" role="alert" tabindex="-1">
        <p class="form-error-text">{{ ui(serverError) }}</p>
        <a class="form-error-link" href="https://t.me/MFS_support" target="_blank" rel="noopener">Telegram: @MFS_support</a>
      </div>
      <p v-if="attempted && Object.keys(errors).length" class="field-error-msg" role="alert">{{ ui('required') }}</p>
      <button type="submit" :disabled="pending" class="btn submit-btn" :class="form.platform ? 'bolt' : 'default'">{{ ui(pending ? 'sending' : 'send') }}</button>
      <div class="consent-row">
        <input id="consent" v-model="form.consent" type="checkbox" class="consent-checkbox" :disabled="pending" :aria-invalid="!!errors.consent" :aria-describedby="errors.consent ? 'consent-error' : undefined" />
        <label for="consent" class="consent-label">{{ t('form.consent.label') }}</label>
      </div>
      <p v-if="errors.consent" id="consent-error" class="field-error-msg">{{ message('consent') }}</p>
      <details class="privacy-note"><summary>{{ ui('privacy') }}</summary><p>{{ ui('privacyText') }}</p></details>
    </form>
  </div>
</template>
