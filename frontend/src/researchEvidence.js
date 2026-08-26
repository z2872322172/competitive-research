const SOURCE_TYPE_LABELS = {
  official: '官方',
  docs: '文档',
  news: '新闻',
  community: '社区',
  upload: '上传',
}

function formatDate(value) {
  if (!value) return '未披露'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function formatLocator(locator) {
  if (!locator || typeof locator !== 'object' || Array.isArray(locator)) return '未记录'
  const entries = Object.entries(locator).filter(([, value]) => value !== null && value !== undefined && value !== '')
  if (!entries.length) return '未记录'
  return entries.map(([key, value]) => `${key}: ${String(value)}`).join(' · ')
}

export function sourceTypeLabel(type) {
  return SOURCE_TYPE_LABELS[type] || '文档'
}

function normalizeFilterValue(value) {
  if (!value || value === 'all') return ''
  return String(value).trim()
}

function uniqueValues(values) {
  return Array.from(new Set(values.filter(Boolean).map((value) => String(value))))
}

function claimEvidenceIds(claim) {
  if (Array.isArray(claim?.evidence_ids)) return claim.evidence_ids
  if (Array.isArray(claim?.evidence)) return claim.evidence
  return []
}

function claimSubject(claim) {
  return claim?.subject || claim?.target || ''
}

function claimDimension(claim) {
  return claim?.dimension || claim?.claim_type || ''
}

function qualityTone(confidence) {
  if (confidence >= 80) return 'high'
  if (confidence >= 55) return 'medium'
  return 'low'
}

export function buildEvidenceQuery(filters = {}) {
  const search = new URLSearchParams()
  const competitor = normalizeFilterValue(filters.competitor)
  const dimension = normalizeFilterValue(filters.dimension)
  const sourceType = normalizeFilterValue(filters.sourceType)
  if (competitor) search.set('evidence_competitor', competitor)
  if (dimension) search.set('evidence_dimension', dimension)
  if (sourceType) search.set('evidence_source_type', sourceType)
  return search.toString()
}

export function filterEvidenceViewModels(items, filters = {}) {
  const sourceType = normalizeFilterValue(filters.sourceType)
  const competitor = normalizeFilterValue(filters.competitor)
  const dimension = normalizeFilterValue(filters.dimension)

  return items.filter((item) => {
    if (sourceType && item.sourceType !== sourceType) return false
    if (competitor && Array.isArray(item.competitors) && !item.competitors.includes(competitor)) return false
    if (dimension && Array.isArray(item.dimensions) && !item.dimensions.includes(dimension)) return false
    return true
  })
}

export function buildEvidenceViewModel(item, claimCount) {
  const source = item.source || {}
  const sourceType = source.source_type || 'docs'
  return {
    id: item.id,
    sourceId: item.source_id,
    sourceType,
    type: sourceTypeLabel(sourceType),
    title: source.title || item.id,
    domain: source.canonical_url || source.url || item.source_id,
    publisher: source.publisher || '未知来源',
    publishedAt: formatDate(source.published_at || null),
    retrievedAt: formatDate(source.retrieved_at || null),
    confidence: Math.round(item.quality_score * 100),
    excerpt: item.quote,
    claims: claimCount,
    sourceUrl: source.url || '',
    canonicalUrl: source.canonical_url || '',
    locatorText: formatLocator(item.locator),
    extractionMethod: item.extraction_method || 'unknown',
    snapshotHint: source.content_hash ? `内容哈希 ${source.content_hash}` : '快照接口待接入',
  }
}

export function buildEvidenceWallItems(items, claims = []) {
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

export function buildEvidenceTraceState(evidence, snapshot, state = {}) {
  const sourceUrl = evidence?.sourceUrl || evidence?.canonicalUrl || ''
  const loading = Boolean(state.loading)
  const error = String(state.error || '').trim()
  let snapshotStatus = 'idle'
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

export function snapshotPreviewText(snapshot, fallbackHint = '') {
  if (!snapshot) return fallbackHint || '快照待加载'
  if (snapshot.available && snapshot.summary) return snapshot.summary
  if (snapshot.available) return '快照已找到，但没有可读摘要'
  return fallbackHint ? `快照暂不可用 · ${fallbackHint}` : '快照暂不可用'
}
