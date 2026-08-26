<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { createDemoCouriers } from './data/couriers'
import type {
  Courier,
  CourierDocument,
  PlatformStatus,
} from './types/courier'

const PAGE_SIZE = 5
const MAX_FILE_SIZE = 10 * 1024 * 1024
const ALLOWED_FILE_TYPES = new Set(['application/pdf', 'image/jpeg', 'image/png'])

const statusLabels: Record<PlatformStatus, string> = {
  active: 'Активен',
  review: 'На проверке',
  blocked: 'Заблокирован',
}

const documentStatusLabels = {
  ready: 'Готов',
  processing: 'На проверке',
  rejected: 'Нужна замена',
} as const

const couriers = ref(createDemoCouriers())
const searchQuery = ref('')
const cityFilter = ref('all')
const statusFilter = ref<'all' | PlatformStatus>('all')
const currentPage = ref(1)
const createOpen = ref(false)
const selectedCourier = ref<Courier | null>(null)
const createLayer = ref<HTMLDivElement | null>(null)
const detailLayer = ref<HTMLDivElement | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const selectedFile = ref<File | null>(null)
const fileError = ref('')
const toastVisible = ref(false)
const lastFocused = ref<HTMLElement | null>(null)
const ownedPreviewUrls = new Set<string>()
let toastTimer: ReturnType<typeof setTimeout> | undefined

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

const filteredCouriers = computed(() => {
  const query = searchQuery.value.trim().toLocaleLowerCase('ru')

  return couriers.value.filter((courier) => {
    const matchesQuery =
      !query ||
      [courier.fullName, courier.email, courier.phone].some((value) =>
        value.toLocaleLowerCase('ru').includes(query),
      )
    const matchesCity = cityFilter.value === 'all' || courier.city === cityFilter.value
    const matchesStatus =
      statusFilter.value === 'all' ||
      courier.platforms.some((platform) => platform.status === statusFilter.value)

    return matchesQuery && matchesCity && matchesStatus
  })
})

const pageCount = computed(() => Math.max(1, Math.ceil(filteredCouriers.value.length / PAGE_SIZE)))
const pageNumbers = computed(() => Array.from({ length: pageCount.value }, (_, index) => index + 1))
const pageStart = computed(() => (currentPage.value - 1) * PAGE_SIZE)
const visibleCouriers = computed(() =>
  filteredCouriers.value.slice(pageStart.value, pageStart.value + PAGE_SIZE),
)
const paginationSummary = computed(() => {
  const total = filteredCouriers.value.length
  const from = total ? pageStart.value + 1 : 0
  const to = Math.min(pageStart.value + PAGE_SIZE, total)
  return `${from}–${to} из ${total}`
})
const filterSummary = computed(() =>
  filteredCouriers.value.length === couriers.value.length
    ? 'Показаны все записи'
    : `Найдено: ${filteredCouriers.value.length}`,
)

watch([searchQuery, cityFilter, statusFilter], () => {
  currentPage.value = 1
})

watch(pageCount, (count) => {
  currentPage.value = Math.min(currentPage.value, count)
})

watch([createOpen, selectedCourier], ([isCreateOpen, courier]) => {
  document.body.classList.toggle('modal-open', isCreateOpen || Boolean(courier))
})

function pageTo(page: number) {
  currentPage.value = Math.min(Math.max(page, 1), pageCount.value)
}

async function focusModal(layer: typeof createLayer) {
  await nextTick()
  layer.value
    ?.querySelector<HTMLElement>('input:not([disabled]), button:not([disabled]), select:not([disabled])')
    ?.focus()
}

function rememberFocus(trigger?: EventTarget | null) {
  lastFocused.value = trigger instanceof HTMLElement ? trigger : document.activeElement as HTMLElement | null
}

function restoreFocus() {
  void nextTick(() => lastFocused.value?.focus())
}

function openCreate(event: MouseEvent) {
  rememberFocus(event.currentTarget)
  selectedCourier.value = null
  createOpen.value = true
  void focusModal(createLayer)
}

function closeCreate() {
  createOpen.value = false
  restoreFocus()
}

function openDetails(courier: Courier, event: MouseEvent) {
  rememberFocus(event.currentTarget)
  createOpen.value = false
  selectedCourier.value = courier
  void focusModal(detailLayer)
}

function closeDetails() {
  selectedCourier.value = null
  restoreFocus()
}

function closeActiveModal() {
  if (createOpen.value) closeCreate()
  else if (selectedCourier.value) closeDetails()
}

function onLayerKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    closeActiveModal()
    return
  }
  if (event.key !== 'Tab') return

  const layer = event.currentTarget as HTMLElement
  const focusable = Array.from(
    layer.querySelectorAll<HTMLElement>(
      'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href]',
    ),
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

function resetForm() {
  Object.assign(form, initialForm())
  for (const key of Object.keys(formErrors) as Array<keyof typeof formErrors>) {
    formErrors[key] = false
  }
  selectedFile.value = null
  fileError.value = ''
  if (fileInput.value) fileInput.value.value = ''
}

function showToast() {
  toastVisible.value = true
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => {
    toastVisible.value = false
  }, 4_200)
}

function submitCourier() {
  if (!validateForm()) return

  const courierId = crypto.randomUUID().slice(0, 8)
  const createdAt = new Date().toISOString()
  let uploadedDocument: CourierDocument | null = null

  if (selectedFile.value) {
    const previewUrl = URL.createObjectURL(selectedFile.value)
    ownedPreviewUrls.add(previewUrl)
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

  const created: Courier = {
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
  }

  couriers.value.unshift(created)
  searchQuery.value = ''
  cityFilter.value = 'all'
  statusFilter.value = 'all'
  currentPage.value = 1
  closeCreate()
  resetForm()
  showToast()
}

function formatBirthDate(value: string) {
  if (!value) return 'Не указана'
  const [year, month, day] = value.split('-')
  return `${day}.${month}.${year}`
}

function formatFileSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} КБ`
  return `${(bytes / 1024 / 1024).toLocaleString('ru-RU', { maximumFractionDigits: 1 })} МБ`
}

function formatDocumentDate(value: string) {
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(new Date(value))
}

function fileFormat(document: CourierDocument) {
  if (document.file.contentType === 'application/pdf') return 'PDF'
  return document.file.contentType.replace('image/', '').toLocaleUpperCase('ru') || 'FILE'
}

onBeforeUnmount(() => {
  document.body.classList.remove('modal-open')
  if (toastTimer) clearTimeout(toastTimer)
  ownedPreviewUrls.forEach((url) => URL.revokeObjectURL(url))
})
</script>

<template>
  <header class="topnav" data-od-id="topnav">
    <div class="container topnav-inner">
      <a class="brand" href="#content" data-od-id="brand-home" aria-label="MFS — главная">
        <span class="brand-copy">
          <strong>May Fleet Solutions</strong>
          <span>Операционная панель</span>
        </span>
      </a>
      <nav class="tabs" aria-label="Разделы панели">
        <button class="tab" type="button" aria-current="page" data-od-id="tab-couriers">
          Couriers
        </button>
      </nav>
      <div class="account" data-od-id="account-menu">
        <div class="account-copy">
          <strong>Администратор</strong>
          <span>Вена, Австрия</span>
        </div>
        <span class="avatar" aria-hidden="true">АМ</span>
      </div>
    </div>
  </header>

  <main id="content">
    <section class="section" data-od-id="couriers-registry">
      <div class="container">
        <div class="row-between page-heading">
          <h1 data-od-id="couriers-title">Курьеры</h1>
          <button class="btn btn-primary" type="button" data-od-id="create-courier" @click="openCreate">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
              <path d="M12 5v14M5 12h14" />
            </svg>
            Создать
          </button>
        </div>

        <div class="toolbar" data-od-id="couriers-filters">
          <label class="control-wrap">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
              <circle cx="11" cy="11" r="6.5" />
              <path d="m16 16 4 4" />
            </svg>
            <span class="visually-hidden">Поиск курьеров</span>
            <input
              v-model="searchQuery"
              class="input"
              type="search"
              placeholder="Имя, email или телефон"
              autocomplete="off"
              data-od-id="courier-search"
            />
          </label>
          <label>
            <span class="visually-hidden">Город</span>
            <select v-model="cityFilter" class="select" data-od-id="city-filter">
              <option value="all">Все города</option>
              <option value="Вена">Вена</option>
              <option value="Грац">Грац</option>
              <option value="Линц">Линц</option>
              <option value="Зальцбург">Зальцбург</option>
            </select>
          </label>
          <label>
            <span class="visually-hidden">Статус платформы</span>
            <select v-model="statusFilter" class="select" data-od-id="status-filter">
              <option value="all">Любой статус</option>
              <option value="active">Активен</option>
              <option value="review">На проверке</option>
              <option value="blocked">Заблокирован</option>
            </select>
          </label>
          <div class="toolbar-note" aria-live="polite">{{ filterSummary }}</div>
        </div>

        <div class="card" data-od-id="couriers-table-card">
          <div class="table-shell">
            <table v-if="visibleCouriers.length" class="ds-table" data-od-id="couriers-table">
              <thead>
                <tr>
                  <th class="col-courier">Курьер</th>
                  <th class="col-contact">Контакты</th>
                  <th class="col-city">Город</th>
                  <th class="col-platform">Платформы</th>
                  <th class="col-docs">Документы</th>
                  <th class="col-consent">Согласие</th>
                  <th class="col-updated">Обновлено</th>
                  <th class="col-action"><span class="visually-hidden">Действия</span></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="courier in visibleCouriers" :key="courier.id" :data-od-id="`courier-row-${courier.id}`">
                  <td data-label="Курьер">
                    <div class="person">
                      <strong>{{ courier.fullName }}</strong>
                      <span class="num">ID {{ courier.id }}</span>
                    </div>
                  </td>
                  <td data-label="Контакты">
                    <div class="contact-cell">
                      <a :href="`mailto:${courier.email}`">{{ courier.email }}</a>
                      <span class="num">{{ courier.phone }}</span>
                    </div>
                  </td>
                  <td class="city-cell" data-label="Город">{{ courier.city || '—' }}</td>
                  <td data-label="Платформы">
                    <div v-if="courier.platforms.length" class="tag-list">
                      <span v-for="platform in courier.platforms" :key="platform.name" class="tag">
                        {{ platform.name }}
                      </span>
                    </div>
                    <span v-else class="meta">Не подключены</span>
                  </td>
                  <td data-label="Документы">
                    <span
                      class="status"
                      :class="courier.platforms[0]?.status === 'active' ? 'status-ok' : 'status-warn'"
                    >
                      {{ courier.documents }} · {{ courier.documentStatus }}
                    </span>
                  </td>
                  <td data-label="Согласие">
                    <span class="status" :class="courier.consent ? 'status-ok' : 'status-warn'">
                      {{ courier.consent ? 'Получено' : 'Не получено' }}
                    </span>
                  </td>
                  <td data-label="Обновлено"><span class="num">{{ courier.updated }}</span></td>
                  <td data-label="Действия">
                    <button
                      class="table-action"
                      type="button"
                      :aria-label="`Открыть профиль ${courier.fullName}`"
                      @click="openDetails(courier, $event)"
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                        <circle cx="12" cy="5" r="1" />
                        <circle cx="12" cy="12" r="1" />
                        <circle cx="12" cy="19" r="1" />
                      </svg>
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
            <div v-else class="empty-state">
              <h2>Ничего не найдено</h2>
              <p>Измените запрос или сбросьте один из фильтров.</p>
            </div>
          </div>

          <div class="pagination" data-od-id="couriers-pagination">
            <span class="pagination-summary num">{{ paginationSummary }}</span>
            <div class="page-list" aria-label="Страницы">
              <button
                v-for="page in pageNumbers"
                :key="page"
                class="page-button"
                :class="{ active: page === currentPage }"
                type="button"
                :aria-label="`Страница ${page}`"
                :aria-current="page === currentPage ? 'page' : undefined"
                @click="pageTo(page)"
              >
                {{ page }}
              </button>
            </div>
            <div class="pagination-actions">
              <button
                class="btn btn-secondary btn-icon"
                type="button"
                aria-label="Предыдущая страница"
                :disabled="currentPage === 1"
                @click="pageTo(currentPage - 1)"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                  <path d="m15 18-6-6 6-6" />
                </svg>
              </button>
              <button
                class="btn btn-secondary btn-icon"
                type="button"
                aria-label="Следующая страница"
                :disabled="currentPage === pageCount || filteredCouriers.length === 0"
                @click="pageTo(currentPage + 1)"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                  <path d="m9 6 6 6-6 6" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  </main>

  <Teleport to="body">
    <div
      v-if="createOpen"
      ref="createLayer"
      class="modal-layer"
      @mousedown.self="closeCreate"
      @keydown="onLayerKeydown"
    >
      <div class="modal" role="dialog" aria-modal="true" aria-labelledby="createTitle" data-od-id="create-courier-dialog">
        <div class="modal-header">
          <div class="row-between">
            <div>
              <h2 id="createTitle">Новый курьер</h2>
              <p>Заполните профиль. Платформу и документ можно добавить сразу или позже.</p>
            </div>
            <button class="btn btn-ghost btn-icon" type="button" aria-label="Закрыть" @click="closeCreate">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
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
                  <input id="fullName" v-model="form.fullName" class="input" autocomplete="name" placeholder="Например, Анна Коваль" :aria-invalid="formErrors.fullName" aria-describedby="fullNameError" />
                  <span id="fullNameError" class="field-error">Укажите имя курьера.</span>
                </div>
                <div class="field" :class="{ invalid: formErrors.birthDate }">
                  <label class="required" for="birthDate">Дата рождения</label>
                  <input id="birthDate" v-model="form.birthDate" class="input" type="date" :aria-invalid="formErrors.birthDate" aria-describedby="birthDateError" />
                  <span id="birthDateError" class="field-error">Укажите дату рождения.</span>
                </div>
                <div class="field" :class="{ invalid: formErrors.email }">
                  <label class="required" for="email">Email</label>
                  <input id="email" v-model="form.email" class="input" type="email" autocomplete="email" placeholder="courier@example.com" :aria-invalid="formErrors.email" aria-describedby="emailError" />
                  <span id="emailError" class="field-error">Введите корректный email.</span>
                </div>
                <div class="field" :class="{ invalid: formErrors.phone }">
                  <label class="required" for="phone">Телефон</label>
                  <input id="phone" v-model="form.phone" class="input" type="tel" autocomplete="tel" placeholder="+43 660 000 0000" :aria-invalid="formErrors.phone" aria-describedby="phoneError" />
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
                  <input id="citizenship" v-model="form.citizenship" class="input" placeholder="Страна" />
                </div>
                <div class="field field-wide">
                  <label for="address">Адрес</label>
                  <input id="address" v-model="form.address" class="input" autocomplete="street-address" placeholder="Улица, дом, индекс" />
                </div>
                <div class="field">
                  <label for="bankAccount">Банковский счёт</label>
                  <input id="bankAccount" v-model="form.bankAccount" class="input num" placeholder="AT00 0000 0000 0000 0000" />
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
                  <input id="contact" v-model="form.contact" class="input" placeholder="@username или номер" />
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
                <input ref="fileInput" type="file" accept=".pdf,.jpg,.jpeg,.png" @change="onFileChange" />
              </div>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" type="button" @click="closeCreate">Отмена</button>
            <button class="btn btn-primary" type="submit" data-od-id="submit-courier">Создать курьера</button>
          </div>
        </form>
      </div>
    </div>
  </Teleport>

  <Teleport to="body">
    <div
      v-if="selectedCourier"
      ref="detailLayer"
      class="modal-layer"
      @mousedown.self="closeDetails"
      @keydown="onLayerKeydown"
    >
      <div class="modal modal-detail" role="dialog" aria-modal="true" aria-labelledby="detailTitle" data-od-id="courier-detail-dialog">
        <div class="modal-header">
          <div class="row-between">
            <div>
              <p class="eyebrow">Профиль курьера</p>
              <h2 id="detailTitle">{{ selectedCourier.fullName }}</h2>
              <p class="num">ID {{ selectedCourier.id }}</p>
            </div>
            <button class="btn btn-ghost btn-icon" type="button" aria-label="Закрыть" @click="closeDetails">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                <path d="m6 6 12 12M18 6 6 18" />
              </svg>
            </button>
          </div>
        </div>

        <div class="modal-body">
          <div class="detail-grid">
            <div class="detail-item"><span>Email</span><strong>{{ selectedCourier.email }}</strong></div>
            <div class="detail-item"><span>Телефон</span><strong class="num">{{ selectedCourier.phone }}</strong></div>
            <div class="detail-item"><span>Дата рождения</span><strong class="num">{{ formatBirthDate(selectedCourier.birthDate) }}</strong></div>
            <div class="detail-item"><span>Город</span><strong>{{ selectedCourier.city || 'Не указан' }}</strong></div>
            <div class="detail-item"><span>Гражданство</span><strong>{{ selectedCourier.citizenship || 'Не указано' }}</strong></div>
            <div class="detail-item"><span>Банковский счёт</span><strong class="num">{{ selectedCourier.bank || 'Не указан' }}</strong></div>
            <div class="detail-item"><span>Канал связи</span><strong>{{ selectedCourier.contactPlatform || 'Не указан' }} · {{ selectedCourier.contact || '—' }}</strong></div>
            <div class="detail-item"><span>Источник</span><strong>{{ selectedCourier.source || 'Не указан' }}</strong></div>
            <div class="detail-item"><span>Адрес</span><strong>{{ selectedCourier.address || 'Не указан' }}</strong></div>
            <div class="detail-item"><span>Согласие</span><strong>{{ selectedCourier.consent ? 'Получено' : 'Не получено' }}</strong></div>
          </div>

          <div class="detail-group">
            <div class="row-between"><h3>Платформы</h3><span class="meta">{{ selectedCourier.platforms.length }}</span></div>
            <div class="detail-list">
              <div v-for="platform in selectedCourier.platforms" :key="platform.name" class="detail-row">
                <div><strong>{{ platform.name }}</strong><span>Аккаунт платформы доставки</span></div>
                <span class="status" :class="platform.status === 'active' ? 'status-ok' : 'status-warn'">
                  {{ statusLabels[platform.status] }}
                </span>
              </div>
              <div v-if="!selectedCourier.platforms.length" class="detail-row">
                <div><strong>Платформы не подключены</strong><span>Добавьте аккаунт после проверки профиля.</span></div>
              </div>
            </div>
          </div>

          <div class="detail-group">
            <div class="row-between"><h3>Документы</h3><span class="meta">{{ selectedCourier.documentFiles.length }}</span></div>
            <div v-if="selectedCourier.documentFiles.length" class="document-list">
              <article v-for="document in selectedCourier.documentFiles" :key="document.id" class="document-card" :data-od-id="`document-card-${document.id}`">
                <div class="document-thumb">
                  <img v-if="document.file.previewUrl && document.file.contentType.startsWith('image/')" :src="document.file.previewUrl" :alt="`Миниатюра файла ${document.file.originalName}`" />
                  <embed v-else-if="document.file.previewUrl && document.file.contentType === 'application/pdf'" :src="`${document.file.previewUrl}#toolbar=0&navpanes=0&scrollbar=0`" type="application/pdf" :aria-label="`Миниатюра файла ${document.file.originalName}`" />
                  <div v-else class="document-preview-page" role="img" :aria-label="`Миниатюра файла ${document.file.originalName}`">
                    <span class="preview-file-type">{{ fileFormat(document) }}</span>
                    <span class="preview-header"></span>
                    <span class="preview-identity">
                      <span class="preview-photo">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
                          <circle cx="12" cy="8" r="3" />
                          <path d="M6.5 19c.6-3.1 2.4-5 5.5-5s4.9 1.9 5.5 5" />
                        </svg>
                      </span>
                      <span class="preview-lines"><span class="preview-line"></span><span class="preview-line preview-line-short"></span><span class="preview-line"></span></span>
                    </span>
                    <span class="preview-lines"><span class="preview-line"></span><span class="preview-line"></span><span class="preview-line preview-line-short"></span></span>
                    <span class="preview-stamp">MFS</span>
                  </div>
                </div>
                <div class="document-info">
                  <div class="row-between document-title">
                    <div>
                      <strong :title="document.file.originalName">{{ document.file.originalName }}</strong>
                      <p>{{ document.typeLabel }} · {{ document.purposeLabel }}</p>
                    </div>
                    <span class="status" :class="document.reviewStatus === 'ready' ? 'status-ok' : 'status-warn'">
                      {{ documentStatusLabels[document.reviewStatus] }}
                    </span>
                  </div>
                  <div class="document-meta">
                    <div><span>Формат</span><strong>{{ fileFormat(document) }}</strong></div>
                    <div><span>Размер</span><strong class="num">{{ formatFileSize(document.file.size) }}</strong></div>
                    <div><span>Добавлен</span><strong class="num">{{ formatDocumentDate(document.createdAt) }}</strong></div>
                    <div><span>Файл</span><strong>{{ document.file.status === 'AVAILABLE' ? 'Доступен' : 'Обрабатывается' }}</strong></div>
                  </div>
                  <span class="document-file-id">FILE {{ document.file.id }}</span>
                </div>
              </article>
            </div>
            <div v-else class="document-empty">
              <strong>Документы ещё не загружены</strong>
              <span>Файлы появятся здесь после добавления в профиль.</span>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" type="button" @click="closeDetails">Закрыть</button>
        </div>
      </div>
    </div>
  </Teleport>

  <Teleport to="body">
    <div v-if="toastVisible" class="toast" role="status" aria-live="polite">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
        <path d="m5 12 4 4L19 6" />
      </svg>
      <div><strong>Курьер создан</strong><span>Новая запись добавлена в начало реестра.</span></div>
    </div>
  </Teleport>
</template>
