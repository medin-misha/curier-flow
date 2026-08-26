import type { AccessToken, Admin, LoginCredentials } from '../types/auth'
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

export function getCurrentAdmin() {
  return apiRequest<Admin>('/admin/admins/me')
}

export function logoutAdmin() {
  return apiRequest<void>('/admin/auth/logout', {
    method: 'POST',
    auth: false,
    retryAuth: false,
  })
}
