export type PlatformStatus = 'active' | 'review' | 'blocked'
export type DocumentReviewStatus = 'ready' | 'processing' | 'rejected'
export type FileStatus = 'AVAILABLE' | 'PROCESSING'

export interface CourierPlatform {
  name: string
  status: PlatformStatus
}
export interface CourierFile {
  id: string
  originalName: string
  contentType: string
  size: number
  status: FileStatus
  ownerId: string
  createdAt: string
  previewUrl?: string
}

export interface CourierDocument {
  id: string
  typeLabel: string
  purposeLabel: string
  reviewStatus: DocumentReviewStatus
  file: CourierFile
  createdAt: string
  updatedAt: string
}

export interface Courier {
  id: string
  fullName: string
  email: string
  phone: string
  birthDate: string
  city: string | null
  address: string | null
  citizenship: string | null
  bank: string | null
  contactPlatform: string | null
  contact: string | null
  source: string | null
  consent: boolean
  platforms: CourierPlatform[]
  documents: number
  documentFiles: CourierDocument[]
  documentStatus: string
  updated: string
}
