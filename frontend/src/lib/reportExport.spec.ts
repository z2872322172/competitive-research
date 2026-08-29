import { describe, expect, it } from 'vitest'

import { buildReportExportDescriptor, buildReportExportFilename } from './reportExport'

describe('buildReportExportDescriptor', () => {
  it('resolves pdf and docx metadata', () => {
    expect(buildReportExportDescriptor('pdf').extension).toBe('pdf')
    expect(buildReportExportDescriptor('docx').mimeType).toBe(
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    )
  })
})

describe('buildReportExportFilename', () => {
  it('keeps the report title and extension', () => {
    expect(buildReportExportFilename('Trae 竞品分析', 'pdf')).toBe('Trae 竞品分析.pdf')
  })
})
