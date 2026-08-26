const RISKY_STATUSES = new Set(['conflict', 'undisclosed', 'low_confidence', 'needs_evidence'])
const LOW_RISK_CONFIDENCE_THRESHOLD = 0.8
const LOW_RISK_COVERAGE_THRESHOLD = 0.8
export const LOW_RISK_REVIEW_REASON = '批量接受：低风险 Claim 已达到置信度和引用覆盖率阈值。'

const STATUS_LABELS = {
  verified: '已验证',
  low_confidence: '低置信度',
  conflict: '存在冲突',
  undisclosed: '未披露',
  needs_evidence: '待补证',
}

function confidenceLabel(confidence) {
  if (confidence === 'high') return '高'
  if (confidence === 'low') return '低'
  if (confidence === 'conflict') return '冲突'
  return '中'
}

function kindForStatus(status) {
  if (status === 'conflict') return '冲突'
  if (status === 'undisclosed') return '未披露'
  return '低置信度'
}

function recommendationForStatus(status) {
  if (status === 'conflict') return '优先采用可信度更高的官方来源，并保留冲突说明。'
  if (status === 'undisclosed') return '保留事实边界，不做无依据推断。'
  return '保留事实边界，不做无依据推断。'
}

function isReviewVisible(claim) {
  if (!RISKY_STATUSES.has(claim.status)) return false
  return !claim.review_decision || claim.review_decision === 'continue_research'
}

function buildEvidenceSummary(evidenceId, evidenceById) {
  const evidence = evidenceById.get(evidenceId)
  if (!evidence) return { id: evidenceId, label: `${evidenceId} · 未加载证据` }
  const type = evidence.type || evidence.sourceType || '证据'
  const confidence = evidence.confidence ?? evidence.confidenceScore ?? evidence.quality_score
  const confidenceText = typeof confidence === 'number' ? `${Math.round(confidence)}%` : String(confidence || '')
  return {
    id: evidence.id,
    label: `${evidence.id} · ${type} · ${confidenceText} · ${evidence.title}`,
  }
}

export function buildClaimQualitySnapshot(claim, evidences = []) {
  const evidenceById = new Map(evidences.map((item) => [item.id, item]))
  const evidenceSummaries = (claim.evidence_ids || []).map((evidenceId) => buildEvidenceSummary(evidenceId, evidenceById))

  return {
    confidencePercent: Math.round((claim.confidence_score ?? 0) * 100),
    coveragePercent: Math.round((claim.evidence_coverage ?? 0) * 100),
    statusLabel: STATUS_LABELS[claim.status] || claim.status || '待补证',
    confidenceLabel: confidenceLabel(claim.confidence),
    evidenceSummaries: evidenceSummaries.length ? evidenceSummaries : [{ id: '', label: '暂无绑定证据' }],
    evidenceCount: evidenceSummaries.length,
  }
}

export function buildClaimQualityJudgement(claim, evidences = []) {
  const snapshot = buildClaimQualitySnapshot(claim, evidences)
  const flags = []
  const confidenceScore = claim.confidence_score ?? 0
  const coverageScore = claim.evidence_coverage ?? 0

  if (claim.status === 'conflict') flags.push('conflict')
  if (claim.status === 'needs_evidence' || claim.status === 'undisclosed') flags.push('missing_evidence')
  if (confidenceScore < LOW_RISK_CONFIDENCE_THRESHOLD) flags.push('low_confidence')
  if (coverageScore < LOW_RISK_COVERAGE_THRESHOLD) flags.push('partial_coverage')

  const riskLevel = flags.includes('conflict') || flags.includes('missing_evidence') ? 'high' : flags.length ? 'medium' : 'low'
  const confidenceText = `${snapshot.confidencePercent}% · ${snapshot.confidenceLabel}`
  const coverageText = `${snapshot.coveragePercent}%`
  const evidenceText = `${snapshot.evidenceCount} 条 Evidence`
  const flagLabels = flags.map((flag) => {
    if (flag === 'conflict') return '存在冲突'
    if (flag === 'missing_evidence') return '证据不足'
    if (flag === 'low_confidence') return '低置信度'
    return '覆盖不足'
  })

  return {
    ...snapshot,
    riskLevel,
    confidenceText,
    coverageText,
    statusText: snapshot.statusLabel,
    evidenceText,
    flags,
    flagLabels,
    evidenceSummaries: snapshot.evidenceSummaries,
  }
}

export function buildReviewItems(claims, evidences) {
  return claims.filter(isReviewVisible).map((claim) => {
    const quality = buildClaimQualitySnapshot(claim, evidences)
    return {
      claimId: claim.id,
      title: claim.display_text,
      kind: kindForStatus(claim.status),
      summary: claim.display_text,
      sources: quality.evidenceSummaries.map((item) => item.label),
      evidenceSummaries: quality.evidenceSummaries,
      recommendation: recommendationForStatus(claim.status),
      processed: Boolean(claim.review_decision && claim.review_decision !== 'continue_research'),
      reviewDecision: claim.review_decision,
      reviewReason: claim.review_reason,
      reviewedAt: claim.reviewed_at,
      confidenceLabel: quality.confidenceLabel,
      confidencePercent: quality.confidencePercent,
      coveragePercent: quality.coveragePercent,
      statusLabel: quality.statusLabel,
    }
  })
}

export function selectReviewItem(items, claimId = '') {
  if (!items.length) return null
  return items.find((item) => item.claimId === claimId) ?? items[0]
}

export function resolveReviewReason(item, typedReason = '') {
  const reason = String(typedReason).trim()
  return reason || item.recommendation
}

function hasOpenReviewDecision(claim) {
  return !claim.review_decision || claim.review_decision === 'continue_research'
}

export function buildLowRiskReviewCandidates(claims) {
  return claims
    .filter((claim) => {
      if (!claim.include_in_report) return false
      if (!hasOpenReviewDecision(claim)) return false
      if (claim.status !== 'verified') return false
      if ((claim.confidence_score ?? 0) < LOW_RISK_CONFIDENCE_THRESHOLD) return false
      if ((claim.evidence_coverage ?? 0) < LOW_RISK_COVERAGE_THRESHOLD) return false
      return (claim.evidence_ids?.length ?? 0) > 0
    })
    .map((claim) => ({
      claimId: claim.id,
      title: claim.display_text,
      reason: LOW_RISK_REVIEW_REASON,
    }))
}
