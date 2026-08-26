import assert from 'node:assert/strict'
import { test } from 'node:test'

import { buildReportExportDescriptor, buildReportExportFilename } from './researchExport.js'

test('buildReportExportDescriptor resolves pdf and docx metadata', () => {
  assert.equal(buildReportExportDescriptor('pdf').extension, 'pdf')
  assert.equal(
    buildReportExportDescriptor('docx').mimeType,
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  )
})

test('buildReportExportFilename keeps the report title and extension', () => {
  assert.equal(buildReportExportFilename('Trae 竞品分析', 'pdf'), 'Trae 竞品分析.pdf')
})
