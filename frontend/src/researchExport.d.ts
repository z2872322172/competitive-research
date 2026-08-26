export type ReportExportFormat = 'markdown' | 'pdf' | 'docx'

export type ReportExportDescriptor = {
  extension: string
  mimeType: string
  label: string
}

export function buildReportExportDescriptor(format: string): ReportExportDescriptor

export function buildReportExportFilename(title: string, format: string): string

export function buildReportExportFormats(): Array<ReportExportDescriptor & { format: ReportExportFormat }>
