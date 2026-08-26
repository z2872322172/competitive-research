import type { ClaimOut } from './api'
import type { EvidenceViewModel } from './researchEvidence'

export type ReviewEvidenceSummary = {
  id: number
  label: string
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
}

export type LowRiskReviewCandidate = {
  claimId: number
  title: string
  reason: string
}

export function buildReviewItems(claims: ClaimOut[], evidences: EvidenceViewModel[]): ReviewItemViewModel[]

export function selectReviewItem<T extends { claimId?: number | null }>(items: T[], claimId?: number): T | null

export function resolveReviewReason(item: Pick<ReviewItemViewModel, 'recommendation'>, typedReason?: string): string

export function buildLowRiskReviewCandidates(claims: ClaimOut[]): LowRiskReviewCandidate[]

export function buildClaimQualitySnapshot(claim: ClaimOut, evidences?: EvidenceViewModel[]): ClaimQualitySnapshot

export function buildClaimQualityJudgement(claim: ClaimOut, evidences?: EvidenceViewModel[]): ClaimQualityJudgement
