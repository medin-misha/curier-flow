export interface Receipt {
  id: string
  fileId: string
  amount: string
  date: string
  createdAt: string
  updatedAt: string
}

export interface ReceiptCreateInput {
  fileId: string
  amount: string
  date: string
}

export interface ReceiptPatchInput {
  fileId?: string
  amount?: string
  date?: string
}

export interface ReceiptFormInput {
  amount: string
  date: string
  file: File | null
}

export interface ReceiptYearSummary {
  year: number
  amount: string
  count: number
}
