export type ReportExportFormat = 'markdown' | 'pdf' | 'docx'

export type ReportExportDescriptor = {
  extension: string
  mimeType: string
  label: string
}

const EXPORT_DESCRIPTORS: Record<string, ReportExportDescriptor> = {
  markdown: {
    extension: 'md',
    mimeType: 'text/markdown;charset=utf-8',
    label: 'Markdown',
  },
  pdf: {
    extension: 'pdf',
    mimeType: 'application/pdf',
    label: 'PDF',
  },
  docx: {
    extension: 'docx',
    mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    label: 'DOCX',
  },
}

export function buildReportExportDescriptor(format: string): ReportExportDescriptor {
  return EXPORT_DESCRIPTORS[format] || EXPORT_DESCRIPTORS.markdown
}

export function buildReportExportFilename(title: string, format: string): string {
  const descriptor = buildReportExportDescriptor(format)
  const safeTitle = String(title || 'competitive-research-report')
    .trim()
    .replace(/[<>:"/\\|?*]+/g, '-')
    .replace(/\s+/g, ' ')
    .trim() || 'competitive-research-report'
  return `${safeTitle}.${descriptor.extension}`
}

export function buildReportExportFormats(): Array<ReportExportDescriptor & { format: ReportExportFormat }> {
  return (['markdown', 'pdf', 'docx'] as const).map((format) => ({
    format,
    ...buildReportExportDescriptor(format),
  }))
}
