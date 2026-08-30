export interface StoredFile {
  id: string
  originalName: string
  contentType: string
  size: number
  status: string
  etag: string | null
  ownerId: string | null
  createdAt: string
  downloadUrl: string | null
}
