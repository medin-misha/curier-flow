import type { AccessToken, LoginCredentials } from '../types/auth'
import { mapAdmin, type AdminResponse } from './admins'
import { apiRequest, jsonBody } from './client'

export function loginAdmin(credentials: LoginCredentials) {
  return apiRequest<AccessToken>('/admin/auth/login', {
    method: 'POST',
    auth: false,
    retryAuth: false,
    ...jsonBody(credentials),
  })
}

export function refreshAdminSession() {
  return apiRequest<AccessToken>('/admin/auth/refresh', {
    method: 'POST',
    auth: false,
    retryAuth: false,
  })
}

export async function getCurrentAdmin() {
  return mapAdmin(await apiRequest<AdminResponse>('/admin/admins/me'))
}

export function logoutAdmin() {
  return apiRequest<void>('/admin/auth/logout', {
    method: 'POST',
    auth: false,
    retryAuth: false,
  })
}
