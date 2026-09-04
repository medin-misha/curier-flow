export type DocumentTemplateFields = Record<string, string[]>
export type DocumentRenderValues = Record<string, Record<string, string>>
export type DocumentModelGroup = 'courier' | 'transport' | 'transport_courier'
export type DocumentValueSource = 'empty' | 'model' | 'manual'

export interface DocumentTemplate {
  id: string
  name: string
  fileId: string
  fields: DocumentTemplateFields
  createdAt: string
  updatedAt: string
}

export interface DocumentTemplateCreateInput {
  name: string
  fileId: string
}

export interface DocumentTemplateFormInput {
  name: string
  file: File
}
