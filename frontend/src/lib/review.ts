import type { ClaimOut } from '@/api/types'
import type { EvidenceViewModel } from './evidence'

export type ReviewEvidenceSummary = {
  id: number
  label: string
  relation?: string
  weight?: number
  sourceTitle?: string
  sourceUrl?: string
  reliabilityLabel?: string
  reliabilityScore?: number
}

export type ClaimQualitySnapshot = {
  confidencePercent: number
  coveragePercent: number
  statusLabel: string
  confidenceLabel: string
  evidenceSummaries: ReviewEvidenceSummary[]
  evidenceCount: number
}

export type ClaimQualityJudgement = ClaimQualitySnapshot & {
  riskLevel: 'low' | 'medium' | 'high'
  confidenceText: string
  coverageText: string
  statusText: string
  evidenceText: string
  flags: Array<'conflict' | 'missing_evidence' | 'low_confidence' | 'partial_coverage'>
  flagLabels: string[]
}

export type ReviewItemViewModel = {
  claimId?: number
  title: string
  kind: string
  summary: string
  sources: string[]
  evidenceSummaries: ReviewEvidenceSummary[]
  recommendation: string
  processed?: boolean
  reviewDecision?: string | null
  reviewReason?: string | null
  reviewedAt?: string | null
  confidencePercent: number
  coveragePercent: number
  statusLabel: string
  confidenceLabel: string
  conflictAnalysis?: ClaimOut['conflict_analysis']
}

export type LowRiskReviewCandidate = {
  claimId: number
  title: string
  reason: string
}

export type ClaimEvidenceGroup = {
  relation: 'supports' | 'conflicts' | 'context'
  label: string
  items: ReviewEvidenceSummary[]
}

const RISKY_STATUSES = new Set(['conflict', 'undisclosed', 'low_confidence', 'needs_evidence'])
const LOW_RISK_CONFIDENCE_THRESHOLD = 0.8
const LOW_RISK_COVERAGE_THRESHOLD = 0.8
export const LOW_RISK_REVIEW_REASON = '批量接受：低风险 Claim 已达到置信度和引用覆盖率阈值。'

const STATUS_LABELS: Record<string, string> = {
  verified: '已验证',
  corroborated: '多源印证',
  low_confidence: '低置信度',
  conflict: '存在冲突',
  undisclosed: '未披露',
  needs_evidence: '待补证',
}

const SAFE_STATUSES = new Set(['verified', 'corroborated'])

function confidenceLabel(confidence: string): string {
  if (confidence === 'high') return '高'
  if (confidence === 'low') return '低'
  if (confidence === 'conflict') return '冲突'
  return '中'
}

function kindForStatus(status: string): string {
  if (status === 'conflict') return '冲突'
  if (status === 'undisclosed') return '未披露'
  return '低置信度'
}

function recommendationForStatus(status: string): string {
  if (status === 'conflict') return '优先采用可信度更高的官方来源，并保留冲突说明。'
  if (status === 'undisclosed') return '保留事实边界，不做无依据推断。'
  return '保留事实边界，不做无依据推断。'
}

function isReviewVisible(claim: ClaimOut): boolean {
  if (!RISKY_STATUSES.has(claim.status)) return false
  return !claim.review_decision || claim.review_decision === 'continue_research'
}

function buildEvidenceSummary(evidenceId: number, evidenceById: Map<number, EvidenceViewModel>): ReviewEvidenceSummary {
  const evidence = evidenceById.get(evidenceId)
  if (!evidence) return { id: evidenceId, label: `${evidenceId} · 未加载证据` }
  const type = evidence.type || evidence.sourceType || '证据'
  const confidence = evidence.confidence ?? (evidence as EvidenceViewModel & { confidenceScore?: number; quality_score?: number }).confidenceScore
  const confidenceText = typeof confidence === 'number' ? `${Math.round(confidence)}%` : String(confidence || '')
  return {
    id: evidence.id,
    label: `${evidence.id} · ${type} · ${confidenceText} · ${evidence.title}`,
    sourceTitle: evidence.title,
    sourceUrl: evidence.sourceUrl || evidence.canonicalUrl,
    reliabilityLabel: evidence.reliabilityLabel,
    reliabilityScore: evidence.reliabilityScore,
  }
}

function claimEvidenceLinks(claim: ClaimOut): Array<{ evidence_id: number; relation: string; weight: number }> {
  if (claim.evidence_links?.length) return claim.evidence_links
  return (claim.evidence_ids || []).map((evidenceId) => ({ evidence_id: evidenceId, relation: 'supports', weight: 1 }))
}

export function buildClaimQualitySnapshot(claim: ClaimOut, evidences: EvidenceViewModel[] = []): ClaimQualitySnapshot {
  const evidenceById = new Map(evidences.map((item) => [item.id, item]))
  const evidenceSummaries = claimEvidenceLinks(claim).map((link) => ({
    ...buildEvidenceSummary(link.evidence_id, evidenceById),
    relation: link.relation || 'supports',
    weight: link.weight,
  }))

  return {
    confidencePercent: Math.round((claim.confidence_score ?? 0) * 100),
    coveragePercent: Math.round(((claim as ClaimOut & { evidence_coverage?: number }).evidence_coverage ?? 0) * 100),
    statusLabel: STATUS_LABELS[claim.status] || claim.status || '待补证',
    confidenceLabel: confidenceLabel(claim.confidence),
    evidenceSummaries: evidenceSummaries.length ? evidenceSummaries : [{ id: 0, label: '暂无绑定证据' }],
    evidenceCount: evidenceSummaries.length,
  }
}

export function buildClaimEvidenceGroups(claim: ClaimOut, evidences: EvidenceViewModel[] = []): ClaimEvidenceGroup[] {
  const evidenceById = new Map(evidences.map((item) => [item.id, item]))
  const labels: Record<ClaimEvidenceGroup['relation'], string> = {
    supports: '支持证据',
    conflicts: '冲突证据',
    context: '背景证据',
  }
  const grouped: Record<ClaimEvidenceGroup['relation'], ReviewEvidenceSummary[]> = {
    supports: [],
    conflicts: [],
    context: [],
  }

  for (const link of claimEvidenceLinks(claim)) {
    const relation = link.relation === 'conflicts' ? 'conflicts' : link.relation === 'context' ? 'context' : 'supports'
    grouped[relation].push({
      ...buildEvidenceSummary(link.evidence_id, evidenceById),
      relation,
      weight: link.weight,
    })
  }

  return (Object.keys(grouped) as ClaimEvidenceGroup['relation'][])
    .filter((relation) => grouped[relation].length > 0)
    .map((relation) => ({ relation, label: labels[relation], items: grouped[relation] }))
}

export function buildClaimQualityJudgement(claim: ClaimOut, evidences: EvidenceViewModel[] = []): ClaimQualityJudgement {
  const snapshot = buildClaimQualitySnapshot(claim, evidences)
  const flags: ClaimQualityJudgement['flags'] = []
  const confidenceScore = claim.confidence_score ?? 0
  const coverageScore = (claim as ClaimOut & { evidence_coverage?: number }).evidence_coverage ?? 0

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

export function buildReviewItems(claims: ClaimOut[], evidences: EvidenceViewModel[]): ReviewItemViewModel[] {
  return claims.filter(isReviewVisible).map((claim) => {
    const quality = buildClaimQualitySnapshot(claim, evidences)
    return {
      claimId: claim.id,
      title: claim.display_text,
      kind: kindForStatus(claim.status),
      summary: claim.display_text,
      sources: quality.evidenceSummaries.map((item) => item.label),
      evidenceSummaries: quality.evidenceSummaries,
      recommendation: claim.conflict_analysis?.recommendation || recommendationForStatus(claim.status),
      processed: Boolean(claim.review_decision && claim.review_decision !== 'continue_research'),
      reviewDecision: claim.review_decision,
      reviewReason: claim.review_reason,
      reviewedAt: claim.reviewed_at,
      conflictAnalysis: claim.conflict_analysis,
      confidenceLabel: quality.confidenceLabel,
      confidencePercent: quality.confidencePercent,
      coveragePercent: quality.coveragePercent,
      statusLabel: quality.statusLabel,
    }
  })
}

export function selectReviewItem<T extends { claimId?: number | null }>(items: T[], claimId: number | string = ''): T | null {
  if (!items.length) return null
  return items.find((item) => item.claimId === claimId) ?? items[0]
}

export function resolveReviewReason(item: Pick<ReviewItemViewModel, 'recommendation'>, typedReason = ''): string {
  const reason = String(typedReason).trim()
  return reason || item.recommendation
}

function hasOpenReviewDecision(claim: ClaimOut): boolean {
  return !claim.review_decision || claim.review_decision === 'continue_research'
}

export function buildLowRiskReviewCandidates(claims: ClaimOut[]): LowRiskReviewCandidate[] {
  return claims
    .filter((claim) => {
      if (!claim.include_in_report) return false
      if (!hasOpenReviewDecision(claim)) return false
      if (!SAFE_STATUSES.has(claim.status)) return false
      if ((claim.confidence_score ?? 0) < LOW_RISK_CONFIDENCE_THRESHOLD) return false
      if (((claim as ClaimOut & { evidence_coverage?: number }).evidence_coverage ?? 0) < LOW_RISK_COVERAGE_THRESHOLD) return false
      return (claim.evidence_ids?.length ?? 0) > 0
    })
    .map((claim) => ({
      claimId: claim.id,
      title: claim.display_text,
      reason: LOW_RISK_REVIEW_REASON,
    }))
}
