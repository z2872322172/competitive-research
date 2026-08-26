const EXPORT_DESCRIPTORS = {
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

export function buildReportExportDescriptor(format) {
  return EXPORT_DESCRIPTORS[format] || EXPORT_DESCRIPTORS.markdown
}

export function buildReportExportFilename(title, format) {
  const descriptor = buildReportExportDescriptor(format)
  const safeTitle = String(title || 'competitive-research-report')
    .trim()
    .replace(/[<>:"/\\|?*]+/g, '-')
    .replace(/\s+/g, ' ')
    .trim() || 'competitive-research-report'
  return `${safeTitle}.${descriptor.extension}`
}

export function buildReportExportFormats() {
  return ['markdown', 'pdf', 'docx'].map((format) => ({
    format,
    ...buildReportExportDescriptor(format),
  }))
}
