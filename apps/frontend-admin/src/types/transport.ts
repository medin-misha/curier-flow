export interface ContractFile {
  id: string
  originalName: string
  contentType: string
  size: number
  status: string
  createdAt: string
}

export interface TransportRental {
  id: string
  transportId: string
  courierId: string
  startedAt: string
  endedAt: string | null
  fileId: string | null
  file: ContractFile | null
  isActive: boolean
  createdAt: string
  updatedAt: string
}

export interface TransportComponent {
  id: string
  transportId: string
  name: string
  unitPrice: string
  quantity: number
  totalPrice: string
  createdAt: string
  updatedAt: string
}

export interface TransportListItem {
  id: string
  type: string
  model: string
  serialNumber: string
  color: string
  depositRequired: boolean
  depositAmount: string | null
  rentalPrice: string
  isAvailable: boolean
  createdAt: string
  updatedAt: string
}

export interface Transport extends TransportListItem {
  components: TransportComponent[]
  activeRental: TransportRental | null
  comment: string | null
  debtAmount: string
}

export interface TransportFilters {
  type: string
  serialNumber: string
  courierId: string
  availability: '' | 'available' | 'rented'
}

export interface TransportInput {
  type: string
  model: string
  serialNumber: string
  color: string
  depositRequired: boolean
  depositAmount: string
  rentalPrice: string
  comment: string
  debtAmount: string
}

export interface TransportComponentInput {
  name: string
  unitPrice: string
  quantity: number
}

export interface TransportRentalInput {
  courierId: string
  startedAt: string
  endedAt: string | null
}
