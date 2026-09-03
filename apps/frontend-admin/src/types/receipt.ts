export interface Receipt {
  id: string
  fileId: string
  amount: string
  date: string
  tagId: string | null
  createdAt: string
  updatedAt: string
}

export interface ReceiptCreateInput {
  fileId: string
  amount: string
  date: string
  tagId: string | null
}

export interface ReceiptPatchInput {
  fileId?: string
  amount?: string
  date?: string
  tagId?: string | null
}

export interface ReceiptFormInput {
  amount: string
  date: string
  tagId: string | null
  file: File | null
}

export interface ReceiptTag {
  id: string
  name: string
  createdAt: string
  updatedAt: string
}

export interface ReceiptTagSummary {
  tagId: string | null
  name: string
  amount: string
  count: number
}

export interface ReceiptMonthSummary {
  month: number
  amount: string
  count: number
}

export interface ReceiptYearSummary {
  year: number
  amount: string
  count: number
  months: ReceiptMonthSummary[]
  tags: ReceiptTagSummary[]
}
