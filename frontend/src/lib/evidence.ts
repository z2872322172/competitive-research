import type { EvidenceOut, SourceSnapshotOut } from '@/api/types'

export type EvidenceViewModel = {
  id: number
  sourceId: number
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
  claimTags?: { id: number | string; label: string }[]
  boundClaims?: { id: number | string; label: string; title: string; status: string }[]
  reliabilityScore?: number
  reliabilityLabel?: string
  reliabilityReasons?: string[]
  reliabilityWarnings?: string[]
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

export type EvidenceFilterOptions = {
  sourceTypes: string[]
  competitors: string[]
  dimensions: string[]
}

type EvidenceFilters = {
  competitor?: string
  dimension?: string
  sourceType?: string
}

// buildEvidenceWallItems 兼容后端 ClaimOut 与前端 Claim 视图模型两种形态。
type ClaimLike = {
  id?: number | string
  subject?: string
  target?: string
  dimension?: string
  claim_type?: string
  display_text?: string
  title?: string
  predicate?: string
  status?: string
  evidence_ids?: number[]
  evidence?: number[]
}

const SOURCE_TYPE_LABELS: Record<string, EvidenceViewModel['type']> = {
  official: '官方',
  docs: '文档',
  news: '新闻',
  community: '社区',
  upload: '上传',
}

function formatDate(value: string | null): string {
  if (!value) return '未披露'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function formatLocator(locator: Record<string, unknown> | null): string {
  if (!locator || typeof locator !== 'object' || Array.isArray(locator)) return '未记录'
  const entries = Object.entries(locator).filter(([, value]) => value !== null && value !== undefined && value !== '')
  if (!entries.length) return '未记录'
  return entries.map(([key, value]) => `${key}: ${String(value)}`).join(' · ')
}

export function sourceTypeLabel(type: string): EvidenceViewModel['type'] {
  return SOURCE_TYPE_LABELS[type] || '文档'
}

function normalizeFilterValue(value?: string): string {
  if (!value || value === 'all') return ''
  return String(value).trim()
}

function uniqueValues(values: Array<string | undefined>): string[] {
  return Array.from(new Set(values.filter(Boolean).map((value) => String(value))))
}

function claimEvidenceIds(claim: ClaimLike): number[] {
  if (Array.isArray(claim?.evidence_ids)) return claim.evidence_ids
  if (Array.isArray(claim?.evidence)) return claim.evidence
  return []
}

function claimSubject(claim: ClaimLike): string {
  return claim?.subject || claim?.target || ''
}

function claimDimension(claim: ClaimLike): string {
  return claim?.dimension || claim?.claim_type || ''
}

function qualityTone(confidence: number): 'high' | 'medium' | 'low' {
  if (confidence >= 80) return 'high'
  if (confidence >= 55) return 'medium'
  return 'low'
}

export function buildEvidenceQuery(filters: EvidenceFilters = {}): string {
  const search = new URLSearchParams()
  const competitor = normalizeFilterValue(filters.competitor)
  const dimension = normalizeFilterValue(filters.dimension)
  const sourceType = normalizeFilterValue(filters.sourceType)
  if (competitor) search.set('evidence_competitor', competitor)
  if (dimension) search.set('evidence_dimension', dimension)
  if (sourceType) search.set('evidence_source_type', sourceType)
  return search.toString()
}

export function filterEvidenceViewModels<T extends { sourceType?: string; competitors?: string[]; dimensions?: string[] }>(
  items: T[],
  filters: EvidenceFilters = {},
): T[] {
  const sourceType = normalizeFilterValue(filters.sourceType)
  const competitor = normalizeFilterValue(filters.competitor)
  const dimension = normalizeFilterValue(filters.dimension)

  return (items || []).filter((item) => {
    if (sourceType && item.sourceType !== sourceType) return false
    if (competitor && Array.isArray(item.competitors) && !item.competitors.includes(competitor)) return false
    if (dimension && Array.isArray(item.dimensions) && !item.dimensions.includes(dimension)) return false
    return true
  })
}

export function buildEvidenceFilterOptions(
  items: Array<{ sourceType?: string; competitors?: string[]; dimensions?: string[] }> = [],
): EvidenceFilterOptions {
  return {
    sourceTypes: uniqueValues(items.map((item) => item.sourceType)).sort(),
    competitors: uniqueValues(items.flatMap((item) => item.competitors || [])).sort((a, b) => a.localeCompare(b, 'zh-CN')),
    dimensions: uniqueValues(items.flatMap((item) => item.dimensions || [])).sort((a, b) => a.localeCompare(b, 'zh-CN')),
  }
}

export function buildEvidenceViewModel(item: EvidenceOut, claimCount: number): EvidenceViewModel {
  const source = item.source
  const sourceType = source?.source_type || 'docs'
  return {
    id: item.id,
    sourceId: item.source_id,
    sourceType,
    type: sourceTypeLabel(sourceType),
    title: source?.title || String(item.id),
    domain: source?.canonical_url || source?.url || String(item.source_id),
    publisher: source?.publisher || '未知来源',
    publishedAt: formatDate(source?.published_at || null),
    retrievedAt: formatDate(source?.retrieved_at || null),
    confidence: Math.round(item.quality_score * 100),
    excerpt: item.quote,
    claims: claimCount,
    sourceUrl: source?.url || '',
    canonicalUrl: source?.canonical_url || '',
    locatorText: formatLocator(item.locator),
    extractionMethod: item.extraction_method || 'unknown',
    snapshotHint: source?.content_hash ? `内容哈希 ${source.content_hash}` : '快照接口待接入',
    reliabilityScore: source?.reliability ? Math.round(source.reliability.score * 100) : undefined,
    reliabilityLabel: source?.reliability?.label,
    reliabilityReasons: source?.reliability?.reasons || [],
    reliabilityWarnings: source?.reliability?.warnings || [],
  }
}

export function buildEvidenceWallItems(items: EvidenceViewModel[], claims: ClaimLike[] = []): EvidenceViewModel[] {
  return items.map((item) => {
    const boundClaims = claims.filter((claim) => claimEvidenceIds(claim).includes(item.id))
    const competitors = uniqueValues(boundClaims.map(claimSubject))
    const dimensions = uniqueValues(boundClaims.map(claimDimension))
    const claimTags = boundClaims.map((claim) => ({
      id: claim.id || `${item.id}-${claimSubject(claim)}-${claimDimension(claim)}`,
      label: uniqueValues([claimSubject(claim), claimDimension(claim)]).join(' / ') || '关联 Claim',
    }))

    return {
      ...item,
      competitors,
      dimensions,
      claimTags,
      boundClaims: boundClaims.map((claim) => ({
        id: claim.id || `${item.id}-${claimSubject(claim)}-${claimDimension(claim)}`,
        label: uniqueValues([claimSubject(claim), claimDimension(claim)]).join(' / ') || '关联 Claim',
        title: claim.display_text || claim.title || claim.predicate || '未命名 Claim',
        status: claim.status || '',
      })),
      qualityTone: qualityTone(item.confidence),
      wallMeta: [item.publisher, item.domain].filter(Boolean).join(' · '),
    }
  })
}

export function buildEvidenceTraceState(
  evidence: Pick<EvidenceViewModel, 'sourceId' | 'sourceUrl' | 'canonicalUrl' | 'snapshotHint'> | null | undefined,
  snapshot?: SourceSnapshotOut | null,
  state: { loading?: boolean; error?: string } = {},
): EvidenceTraceState {
  const sourceUrl = evidence?.sourceUrl || evidence?.canonicalUrl || ''
  const loading = Boolean(state.loading)
  const error = String(state.error || '').trim()
  let snapshotStatus: EvidenceTraceState['snapshotStatus'] = 'idle'
  let snapshotText = snapshotPreviewText(snapshot, evidence?.snapshotHint || '')

  if (loading) {
    snapshotStatus = 'loading'
    snapshotText = '快照读取中...'
  } else if (error) {
    snapshotStatus = 'error'
    snapshotText = `快照读取失败：${error}`
  } else if (snapshot) {
    snapshotStatus = snapshot.available ? 'available' : 'unavailable'
  }

  return {
    sourceUrl,
    canOpenSource: Boolean(sourceUrl),
    canLoadSnapshot: Boolean(evidence?.sourceId) && !loading,
    snapshotStatus,
    snapshotText,
  }
}

export function snapshotPreviewText(snapshot: SourceSnapshotOut | null | undefined, fallbackHint = ''): string {
  if (!snapshot) return fallbackHint || '快照待加载'
  if (snapshot.available && snapshot.summary) return snapshot.summary
  if (snapshot.available) return '快照已找到，但没有可读摘要'
  return fallbackHint ? `快照暂不可用 · ${fallbackHint}` : '快照暂不可用'
}
