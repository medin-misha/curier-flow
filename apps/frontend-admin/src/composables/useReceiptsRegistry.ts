import { ref } from 'vue'
import {
  createReceiptTag,
  deleteReceiptTag,
  createReceipt,
  deleteReceipt,
  getReceipt,
  listReceipts,
  listReceiptTags,
  receiptErrorMessage,
  updateReceipt,
  updateReceiptTag,
} from '../api/receipts'
import { ApiError } from '../api/client'
import type {
  Receipt,
  ReceiptCreateInput,
  ReceiptPatchInput,
  ReceiptTag,
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
  const tags = ref<ReceiptTag[]>([])
  const tagsLoading = ref(false)
  const tagsError = ref('')
  const selectedTagId = ref<string | null>(null)
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
      const result = await listReceipts({
        cursor,
        limit: PAGE_SIZE,
        tagId: selectedTagId.value,
      })
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
      yearlyStats.value = aggregateReceiptYears(allReceipts, tags.value)
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

  async function setTagFilter(tagId: string | null) {
    if (selectedTagId.value === tagId) return
    selectedTagId.value = tagId
    await reloadFirstPage()
  }

  async function loadTags() {
    tagsLoading.value = true
    tagsError.value = ''
    try {
      const found: ReceiptTag[] = []
      let cursor: string | null = null
      do {
        const result = await listReceiptTags({ cursor, limit: STATS_PAGE_SIZE })
        found.push(...result.items)
        cursor = result.nextCursor
      } while (cursor)
      tags.value = found.sort((left, right) => left.name.localeCompare(right.name, 'ru'))
    } catch (error) {
      tagsError.value = receiptErrorMessage(error, 'Не удалось загрузить теги расходов.')
    } finally {
      tagsLoading.value = false
    }
  }

  async function createTag(name: string, idempotencyKey: string) {
    const created = await createReceiptTag(name, idempotencyKey)
    await loadTags()
    return created
  }

  async function renameTag(tagId: string, name: string) {
    const updated = await updateReceiptTag(tagId, name)
    await loadTags()
    await loadStats()
    return updated
  }

  async function removeTag(tagId: string) {
    await deleteReceiptTag(tagId)
    if (selectedTagId.value === tagId) selectedTagId.value = null
    await Promise.all([loadTags(), refresh()])
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
    tags,
    tagsLoading,
    tagsError,
    selectedTagId,
    loadPage,
    loadStats,
    pageTo,
    setTagFilter,
    loadTags,
    reloadFirstPage,
    refresh,
    replaceReceipt,
    retrieve: getReceipt,
    create,
    update,
    remove,
    createTag,
    renameTag,
    removeTag,
  }
}
