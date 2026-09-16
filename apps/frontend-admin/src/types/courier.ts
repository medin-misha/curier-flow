export type DeliveryPlatform = 'bolt_food' | 'foodora' | 'wolt'
export type PlatformStatus = 'pending' | 'active' | 'inactive' | 'problem'
export const COURIER_BULK_LIMIT = 100
export type CourierBulkAction = 'delete' | 'status'

export interface CourierBulkStatusInput {
  platform: DeliveryPlatform
  status: PlatformStatus
}

export interface CourierBulkDeleteResult {
  deletedCount: number
}

export interface CourierBulkStatusResult {
  updatedCount: number
  unchangedCount: number
}

export type DocumentReviewStatus = 'ready' | 'processing' | 'rejected'
export type DocumentType =
  | 'passport'
  | 'identity_card'
  | 'residence_permit'
  | 'work_permit'
  | 'driving_license'
  | 'other'
export type DocumentPurpose = 'platform_onboarding' | 'employment_compliance' | 'other'
export type FileStatus = 'pending' | 'ready' | 'deleting'

export interface CourierPlatform {
  id: string
  platform: DeliveryPlatform
  name: string
  status: PlatformStatus
}

export interface CourierFile {
  id: string
  originalName: string
  contentType: string
  size: number
  status: FileStatus
  ownerId: string | null
  createdAt: string
}

export interface CourierDocument {
  id: string
  type: DocumentType
  typeLabel: string
  purpose: DocumentPurpose
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
  consentAt: string | null
  platforms: CourierPlatform[]
  documents: number
  documentFiles: CourierDocument[]
  documentStatus: string
  createdAt: string
  updatedAt: string
  updated: string
}

export interface CourierFormValues {
  fullName: string
  birthDate: string
  email: string
  phone: string
  city: string
  citizenship: string
  address: string
  bankAccount: string
  source: string
  contactPlatform: string
  contact: string
  consent: boolean
}

export interface CourierFormErrors {
  fullName: boolean
  birthDate: boolean
  email: boolean
  phone: boolean
}

export interface CourierCreateInput {
  courier: CourierFormValues
  platform: DeliveryPlatform
  document?: CourierDocumentCreateInput
}

export interface CourierDocumentCreateInput {
  file: File
  type: DocumentType
  purpose: DocumentPurpose
}

export type CourierUpdateInput = CourierFormValues
