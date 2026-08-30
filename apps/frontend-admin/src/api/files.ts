import { apiRequest, jsonBody } from './client'
import type { StoredFile } from '../types/file'

interface FileDetailResponse {
  id: string
  original_name: string
  content_type: string
  size: number
  status: string
  etag: string | null
  owner_id: string | null
  created_at: string
  download_url: string | null
}

function mapStoredFile(file: FileDetailResponse): StoredFile {
  return {
    id: file.id,
    originalName: file.original_name,
    contentType: file.content_type,
    size: file.size,
    status: file.status,
    etag: file.etag,
    ownerId: file.owner_id,
    createdAt: file.created_at,
    downloadUrl: file.download_url,
  }
}

export async function getFileDetails(fileId: string) {
  return mapStoredFile(await apiRequest<FileDetailResponse>(`/files/${fileId}`))
}

export async function getFileDownloadUrl(fileId: string) {
  const file = await apiRequest<FileDetailResponse>(`/files/${fileId}`)
  return file.download_url
}

interface UploadTicketResponse {
  file_id: string
  upload_url: string
  content_type: string
  expires_in: number
}

export function requestFileUpload(file: File) {
  return apiRequest<UploadTicketResponse>('/files/upload-url', {
    method: 'POST',
    ...jsonBody({
      original_name: file.name,
      content_type: file.type,
      size: file.size,
    }),
  })
}

export async function putFile(uploadUrl: string, contentType: string, file: File) {
  const response = await fetch(uploadUrl, {
    method: 'PUT',
    headers: { 'Content-Type': contentType },
    body: file,
    credentials: 'omit',
  })
  if (!response.ok) throw new Error('Хранилище отклонило загрузку файла.')
  const rawEtag = response.headers.get('ETag')
  if (!rawEtag) throw new Error('Хранилище не вернуло ETag загруженного файла.')
  return rawEtag.replace(/^W\//, '').replace(/^"|"$/g, '')
}

export function confirmFileUpload(fileId: string, etag: string) {
  return apiRequest(`/files/${fileId}/confirm`, {
    method: 'POST',
    ...jsonBody({ etag }),
  })
}

export function deleteFile(fileId: string) {
  return apiRequest<void>(`/files/${fileId}`, { method: 'DELETE' })
}
