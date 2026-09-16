import { computed, ref } from 'vue'
import { bulkDeleteCouriers, bulkUpdateCourierStatus, courierBulkErrorMessage } from '../api/couriers'
import { ApiError } from '../api/client'
import {
  COURIER_BULK_LIMIT,
  type Courier,
  type CourierBulkAction,
  type CourierBulkStatusInput,
} from '../types/courier'

export function useCourierBulkActions() {
  const selected = ref<Courier[]>([])
  const selectedIds = computed(() => selected.value.map((courier) => courier.id))
  const busy = ref(false)
  const error = ref('')
  const commandKeys = new Map<string, string>()

  function clearSelection() {
    if (busy.value) return
    selected.value = []
    error.value = ''
  }

  function toggle(courier: Courier) {
    if (busy.value) return
    if (selectedIds.value.includes(courier.id)) {
      selected.value = selected.value.filter((item) => item.id !== courier.id)
    } else if (selected.value.length < COURIER_BULK_LIMIT) {
      selected.value.push(courier)
    }
  }

  function togglePage(couriers: Courier[]) {
    if (busy.value || !couriers.length) return
    const pageIds = new Set(couriers.map((courier) => courier.id))
    if (couriers.every((courier) => selectedIds.value.includes(courier.id))) {
      selected.value = selected.value.filter((courier) => !pageIds.has(courier.id))
      return
    }
    const additions = couriers.filter((courier) => !selectedIds.value.includes(courier.id))
    if (selected.value.length + additions.length <= COURIER_BULK_LIMIT) {
      selected.value.push(...additions)
    }
  }

  function sync(couriers: Courier[]) {
    const fresh = new Map(couriers.map((courier) => [courier.id, courier]))
    selected.value = selected.value.map((courier) => fresh.get(courier.id) ?? courier)
  }

  function forget(courierId: string) {
    selected.value = selected.value.filter((courier) => courier.id !== courierId)
  }

  async function execute<T>(
    action: CourierBulkAction,
    input: CourierBulkStatusInput | null,
    request: (ids: string[], key: string) => Promise<T>,
  ): Promise<T | null> {
    if (busy.value || !selected.value.length || selected.value.length > COURIER_BULK_LIMIT) return null
    const couriers = [...selected.value]
    const ids = couriers.map((courier) => courier.id).sort()
    const signature = JSON.stringify({ action, ids, input })
    busy.value = true
    error.value = ''
    try {
      // Повтор после потери ответа использует тот же ключ и порядок UUID.
      let key = commandKeys.get(signature)
      if (!key) {
        key = crypto.randomUUID()
        commandKeys.set(signature, key)
      }
      const result = await request(ids, key)
      selected.value = []
      commandKeys.clear()
      return result
    } catch (cause) {
      error.value = courierBulkErrorMessage(cause, couriers)
      if (cause instanceof ApiError && cause.problem?.reason === 'payload-mismatch') {
        commandKeys.delete(signature)
      }
      return null
    } finally {
      busy.value = false
    }
  }

  function remove() {
    return execute('delete', null, bulkDeleteCouriers)
  }

  function updateStatus(input: CourierBulkStatusInput) {
    const missingPlatform = selected.value.some(
      (courier) => !courier.platforms.some((account) => account.platform === input.platform),
    )
    if (missingPlatform) {
      error.value = 'У всех выбранных курьеров должна быть регистрация на этой платформе.'
      return Promise.resolve(null)
    }
    return execute('status', input, (ids, key) => bulkUpdateCourierStatus(ids, input, key))
  }

  return {
    selected,
    selectedIds,
    busy,
    error,
    clearSelection,
    toggle,
    togglePage,
    sync,
    forget,
    remove,
    updateStatus,
  }
}
