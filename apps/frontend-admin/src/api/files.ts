import { apiRequest } from './client'

interface FileDetailResponse {
  download_url: string | null
}

export async function getFileDownloadUrl(fileId: string) {
  const file = await apiRequest<FileDetailResponse>(`/files/${fileId}`)
  return file.download_url
}
