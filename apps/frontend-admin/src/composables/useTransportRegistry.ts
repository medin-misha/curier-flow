import { reactive, ref } from 'vue'
import { listTransports, transportErrorMessage } from '../api/transports'
import type { TransportFilters, TransportListItem } from '../types/transport'

const PAGE_SIZE = 5
const emptyFilters = (): TransportFilters => ({
  type: '',
  serialNumber: '',
  courierId: '',
  availability: '',
})

export function useTransportRegistry() {
  const transports = ref<TransportListItem[]>([])
  const draftFilters = reactive<TransportFilters>(emptyFilters())
  const appliedFilters = reactive<TransportFilters>(emptyFilters())
  const currentPage = ref(1)
  const cursors = ref<Array<string | null>>([null])
  const nextCursor = ref<string | null>(null)
  const loading = ref(false)
  const loadError = ref('')
  let loadSequence = 0

  async function loadPage(page: number) {
    const cursor = cursors.value[page - 1]
    if (cursor === undefined) return
    const sequence = ++loadSequence
    currentPage.value = page
    loading.value = true
    loadError.value = ''
    try {
      const result = await listTransports({ cursor, limit: PAGE_SIZE, filters: appliedFilters })
      if (sequence !== loadSequence) return
      transports.value = result.items
      nextCursor.value = result.nextCursor
    } catch (error) {
      if (sequence !== loadSequence) return
      loadError.value = transportErrorMessage(error, 'Не удалось получить список велосипедов.')
    } finally {
      if (sequence === loadSequence) loading.value = false
    }
  }

  async function pageTo(page: number) {
    if (page < 1) return
    if (page === currentPage.value + 1) {
      if (!nextCursor.value) return
      cursors.value[page - 1] = nextCursor.value
    }
    await loadPage(page)
  }

  async function reloadFirstPage() {
    cursors.value = [null]
    nextCursor.value = null
    currentPage.value = 1
    await loadPage(1)
  }

  async function applyFilters() {
    Object.assign(appliedFilters, draftFilters)
    await reloadFirstPage()
  }

  async function clearFilters() {
    Object.assign(draftFilters, emptyFilters())
    Object.assign(appliedFilters, emptyFilters())
    await reloadFirstPage()
  }

  function replaceTransport(updated: TransportListItem) {
    const index = transports.value.findIndex((transport) => transport.id === updated.id)
    if (index >= 0) transports.value[index] = updated
  }

  return {
    transports,
    draftFilters,
    appliedFilters,
    currentPage,
    nextCursor,
    loading,
    loadError,
    loadPage,
    pageTo,
    reloadFirstPage,
    applyFilters,
    clearFilters,
    replaceTransport,
  }
}
