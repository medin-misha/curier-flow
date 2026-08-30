import { ref } from 'vue'
import {
  activateAdmin,
  adminErrorMessage,
  createAdmin,
  deactivateAdmin,
  getAdmin,
  listAdmins,
  resetAdminPassword,
  updateAdmin,
} from '../api/admins'
import type { Admin, AdminCreateInput, AdminUpdateInput } from '../types/admin'

const PAGE_SIZE = 5

export function useAdminsRegistry() {
  const admins = ref<Admin[]>([])
  const currentPage = ref(1)
  const cursors = ref<Array<string | null>>([null])
  const nextCursor = ref<string | null>(null)
  const loading = ref(false)
  const loadError = ref('')
  let loadSequence = 0

  function replaceAdmin(updated: Admin) {
    const index = admins.value.findIndex((admin) => admin.id === updated.id)
    if (index >= 0) admins.value[index] = updated
    return updated
  }

  async function loadPage(page: number) {
    const cursor = cursors.value[page - 1]
    if (cursor === undefined) return

    const sequence = ++loadSequence
    currentPage.value = page
    loading.value = true
    loadError.value = ''
    try {
      const result = await listAdmins({ cursor, limit: PAGE_SIZE })
      if (sequence !== loadSequence) return
      admins.value = result.items
      nextCursor.value = result.nextCursor
    } catch (error) {
      if (sequence !== loadSequence) return
      loadError.value = adminErrorMessage(error, 'Не удалось получить список администраторов.')
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

  async function retrieve(adminId: string) {
    return getAdmin(adminId)
  }

  async function create(input: AdminCreateInput, idempotencyKey: string) {
    const created = await createAdmin(input, idempotencyKey)
    await reloadFirstPage()
    return created
  }

  async function update(adminId: string, input: AdminUpdateInput) {
    return replaceAdmin(await updateAdmin(adminId, input))
  }

  async function setActive(adminId: string, active: boolean) {
    return replaceAdmin(await (active ? activateAdmin(adminId) : deactivateAdmin(adminId)))
  }

  return {
    admins,
    currentPage,
    nextCursor,
    loading,
    loadError,
    loadPage,
    pageTo,
    replaceAdmin,
    retrieve,
    create,
    update,
    setActive,
    resetPassword: resetAdminPassword,
  }
}
