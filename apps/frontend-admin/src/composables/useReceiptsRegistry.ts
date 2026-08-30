import { ref } from 'vue'
import {
  createReceipt,
  deleteReceipt,
  getReceipt,
  listReceipts,
  receiptErrorMessage,
  updateReceipt,
} from '../api/receipts'
import { ApiError } from '../api/client'
import type {
  Receipt,
  ReceiptCreateInput,
  ReceiptPatchInput,
  ReceiptYearSummary,
} from '../types/receipt'
import { aggregateReceiptYears } from './receiptStats'

const PAGE_SIZE = 5
const STATS_PAGE_SIZE = 200

export function useReceiptsRegistry() {
  const receipts = ref<Receipt[]>([])
  const currentPage = ref(1)
  const cursors = ref<Array<string | null>>([null])
  const nextCursor = ref<string | null>(null)
  const loading = ref(false)
  const loadError = ref('')
  const yearlyStats = ref<ReceiptYearSummary[]>([])
  const statsLoading = ref(false)
  const statsError = ref('')
  let loadSequence = 0
  let statsSequence = 0

  async function loadPage(page: number) {
    const cursor = cursors.value[page - 1]
    if (cursor === undefined) return
    const sequence = ++loadSequence
    currentPage.value = page
    loading.value = true
    loadError.value = ''
    try {
      const result = await listReceipts({ cursor, limit: PAGE_SIZE })
      if (sequence !== loadSequence) return
      receipts.value = result.items
      nextCursor.value = result.nextCursor
    } catch (error) {
      if (sequence !== loadSequence) return
      loadError.value = receiptErrorMessage(error, 'Не удалось получить список чеков.')
    } finally {
      if (sequence === loadSequence) loading.value = false
    }
  }

  async function loadStats() {
    const sequence = ++statsSequence
    statsLoading.value = true
    statsError.value = ''
    try {
      const allReceipts: Receipt[] = []
      let cursor: string | null = null
      do {
        const result = await listReceipts({ cursor, limit: STATS_PAGE_SIZE })
        if (sequence !== statsSequence) return
        allReceipts.push(...result.items)
        cursor = result.nextCursor
      } while (cursor)
      yearlyStats.value = aggregateReceiptYears(allReceipts)
    } catch (error) {
      if (sequence !== statsSequence) return
      statsError.value = receiptErrorMessage(error, 'Не удалось рассчитать статистику.')
    } finally {
      if (sequence === statsSequence) statsLoading.value = false
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

  async function refresh() {
    await Promise.all([reloadFirstPage(), loadStats()])
  }

  function replaceReceipt(updated: Receipt) {
    const index = receipts.value.findIndex((receipt) => receipt.id === updated.id)
    if (index >= 0) receipts.value[index] = updated
    return updated
  }

  async function create(input: ReceiptCreateInput, idempotencyKey: string) {
    const created = await createReceipt(input, idempotencyKey)
    await refresh()
    return created
  }

  async function update(receiptId: string, input: ReceiptPatchInput) {
    const updated = replaceReceipt(await updateReceipt(receiptId, input))
    await loadStats()
    return updated
  }

  async function remove(receiptId: string) {
    try {
      await deleteReceipt(receiptId)
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 404) throw error
    }
    await refresh()
  }

  return {
    receipts,
    currentPage,
    nextCursor,
    loading,
    loadError,
    yearlyStats,
    statsLoading,
    statsError,
    loadPage,
    loadStats,
    pageTo,
    reloadFirstPage,
    refresh,
    replaceReceipt,
    retrieve: getReceipt,
    create,
    update,
    remove,
  }
}
