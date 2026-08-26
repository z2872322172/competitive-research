import type { ReportOut, ReportSectionOut } from './api'

export type ReportVersionItem = {
  id: string
  version: number
  label: string
  isLatest: boolean
  reason: string
  reasonLabel: string
  coveragePercent: number
  generatedAt?: string | null
  generatedAtLabel: string
}

export function buildReportVersionItems(reports: ReportOut[]): ReportVersionItem[]

export function selectNewestReportVersion(reports: ReportOut[]): number | null

export type PostReviewReportUpdateState = {
  hasPostReviewUpdate: boolean
  latestVersion: number | null
  selectedVersion: number | null
  isViewingLatest: boolean
  message: string
  actionLabel: string
}

export function buildPostReviewReportUpdateState(
  reports: ReportOut[],
  selectedVersion?: number | null,
): PostReviewReportUpdateState

export type ReportSectionEvidenceItem = {
  id: string
  quote: string
  sourceLabel: string
  sourceUrl: string
  qualityLabel: string
  relation: string
  claimLabel: string
}

export function buildReportSectionEvidenceItems(section: Partial<ReportSectionOut>): ReportSectionEvidenceItem[]
