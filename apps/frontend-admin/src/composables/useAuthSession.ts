import { ref } from 'vue'
import { getCurrentAdmin, loginAdmin, logoutAdmin, refreshAdminSession } from '../api/auth'
import { ApiError, configureAccessRecovery, setAccessToken } from '../api/client'
import type { Admin, LoginCredentials } from '../types/auth'

export type AuthStatus = 'checking' | 'anonymous' | 'authenticated'

export function useAuthSession() {
  const status = ref<AuthStatus>('checking')
  const admin = ref<Admin | null>(null)
  const busy = ref(false)
  const error = ref('')

  function clearSession() {
    setAccessToken(null)
    admin.value = null
    status.value = 'anonymous'
  }

  async function refreshAccess() {
    try {
      const grant = await refreshAdminSession()
      setAccessToken(grant.access_token)
      return true
    } catch {
      clearSession()
      return false
    }
  }

  configureAccessRecovery(refreshAccess)

  async function initialize() {
    status.value = 'checking'
    if (!(await refreshAccess())) return

    try {
      admin.value = await getCurrentAdmin()
      status.value = 'authenticated'
    } catch {
      clearSession()
    }
  }

  async function login(credentials: LoginCredentials) {
    busy.value = true
    error.value = ''
    try {
      const grant = await loginAdmin(credentials)
      setAccessToken(grant.access_token)
      admin.value = await getCurrentAdmin()
      status.value = 'authenticated'
    } catch (caught) {
      clearSession()
      error.value =
        caught instanceof ApiError && caught.status === 401
          ? 'Неверный логин или пароль.'
          : 'Не удалось войти. Проверьте соединение и повторите попытку.'
    } finally {
      busy.value = false
    }
  }

  async function logout() {
    busy.value = true
    try {
      await logoutAdmin()
    } finally {
      busy.value = false
      error.value = ''
      clearSession()
    }
  }

  function syncAdmin(updated: Admin) {
    if (admin.value?.id === updated.id) admin.value = updated
  }

  function dispose() {
    configureAccessRecovery(null)
    setAccessToken(null)
  }

  return {
    admin,
    busy,
    error,
    status,
    initialize,
    login,
    logout,
    syncAdmin,
    dispose,
  }
}
