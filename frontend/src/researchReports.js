const REASON_LABELS = {
  initial_workflow: '初始生成',
  after_review: '审核后生成',
  manual_regenerate: '手动再生成',
}

function generationReason(report) {
  return report.input_snapshot?.report_generation?.reason || 'initial_workflow'
}

export function buildReportVersionItems(reports) {
  const newestVersion = selectNewestReportVersion(reports)
  return [...reports]
    .sort((a, b) => b.version - a.version)
    .map((report) => ({
      id: report.id,
      version: report.version,
      label: `v${report.version}`,
      isLatest: report.version === newestVersion,
      reason: generationReason(report),
      reasonLabel: REASON_LABELS[generationReason(report)] || generationReason(report),
      coveragePercent: Math.round((report.citation_coverage ?? 0) * 100),
      generatedAt: report.generated_at,
      generatedAtLabel: report.generated_at ? new Date(report.generated_at).toLocaleString() : '生成时间未知',
    }))
}

export function selectNewestReportVersion(reports) {
  if (!reports.length) return null
  return Math.max(...reports.map((report) => report.version))
}

export function buildReportSectionEvidenceItems(section) {
  return [...(section.evidence ?? [])]
    .sort((a, b) => String(a.id).localeCompare(String(b.id)))
    .map((evidence) => {
      const claimCount = evidence.claim_ids?.length ?? 0
      return {
        id: evidence.id,
        quote: evidence.quote || '',
        sourceLabel: evidence.source_title || evidence.publisher || evidence.source_id,
        sourceUrl: evidence.source_url || '',
        qualityLabel: `${Math.round((evidence.quality_score ?? 0) * 100)}%`,
        relation: evidence.relation || 'supports',
        claimLabel: `${claimCount} ${claimCount === 1 ? 'Claim' : 'Claims'}`,
      }
    })
}

export function buildPostReviewReportUpdateState(reports, selectedVersion = null) {
  if (!Array.isArray(reports) || !reports.length) {
    return {
      hasPostReviewUpdate: false,
      latestVersion: null,
      selectedVersion,
      isViewingLatest: false,
      message: '',
      actionLabel: '',
    }
  }

  const sorted = [...reports].sort((a, b) => b.version - a.version)
  const latest = sorted[0]
  const previous = sorted[1] ?? null
  const latestVersion = latest.version
  const activeVersion = selectedVersion ?? latestVersion
  const hasPostReviewUpdate = generationReason(latest) === 'after_review' && (!previous || latest.version > previous.version)
  const coveragePercent = Math.round((latest.citation_coverage ?? 0) * 100)

  return {
    hasPostReviewUpdate,
    latestVersion,
    selectedVersion: activeVersion,
    isViewingLatest: activeVersion === latestVersion,
    message: hasPostReviewUpdate ? `审核后已生成 v${latestVersion} 报告，引用覆盖率 ${coveragePercent}%。` : '',
    actionLabel: hasPostReviewUpdate ? `查看 v${latestVersion}` : '',
  }
}
