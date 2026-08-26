import type { EvidenceOut, SourceSnapshotOut } from './api'

export type EvidenceViewModel = {
  id: string
  sourceId: string
  sourceType: string
  type: '官方' | '文档' | '新闻' | '社区' | '上传'
  title: string
  domain: string
  publisher: string
  publishedAt: string
  retrievedAt: string
  confidence: number
  excerpt: string
  claims: number
  conflicts?: boolean
  sourceUrl: string
  canonicalUrl: string
  locatorText: string
  extractionMethod: string
  snapshotHint: string
  competitors?: string[]
  dimensions?: string[]
  claimTags?: { id: string; label: string }[]
  boundClaims?: { id: string; label: string; title: string; status: string }[]
  qualityTone?: 'high' | 'medium' | 'low'
  wallMeta?: string
}

export type EvidenceTraceState = {
  sourceUrl: string
  canOpenSource: boolean
  canLoadSnapshot: boolean
  snapshotStatus: 'idle' | 'loading' | 'error' | 'available' | 'unavailable'
  snapshotText: string
}

export function sourceTypeLabel(type: string): EvidenceViewModel['type']

export function buildEvidenceQuery(filters?: { competitor?: string; dimension?: string; sourceType?: string }): string

export function filterEvidenceViewModels<T extends { sourceType?: string }>(
  items: T[],
  filters?: { competitor?: string; dimension?: string; sourceType?: string },
): T[]

export function buildEvidenceViewModel(item: EvidenceOut, claimCount: number): EvidenceViewModel

export function buildEvidenceTraceState(
  evidence: Pick<EvidenceViewModel, 'sourceId' | 'sourceUrl' | 'canonicalUrl' | 'snapshotHint'> | null | undefined,
  snapshot?: SourceSnapshotOut | null,
  state?: { loading?: boolean; error?: string },
): EvidenceTraceState

export function buildEvidenceWallItems(
  items: EvidenceViewModel[],
  claims?: Array<{
    id?: string
    subject?: string
    target?: string
    dimension?: string
    claim_type?: string
    display_text?: string
    title?: string
    predicate?: string
    status?: string
    evidence_ids?: string[]
    evidence?: string[]
  }>,
): EvidenceViewModel[]

export function snapshotPreviewText(snapshot: SourceSnapshotOut | null | undefined, fallbackHint?: string): string
