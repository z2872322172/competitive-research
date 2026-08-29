import type { ReportOut, ReportSectionOut } from '@/api/types'

export type ReportVersionItem = {
  id: number
  version: number
  label: string
  isLatest: boolean
  reason: string
  reasonLabel: string
  coveragePercent: number
  generatedAt: string | null
  generatedAtLabel: string
}

export type PostReviewReportUpdateState = {
  hasPostReviewUpdate: boolean
  latestVersion: number | null
  selectedVersion: number | null
  isViewingLatest: boolean
  message: string
  actionLabel: string
}

export type ReportSectionEvidenceItem = {
  id: number
  quote: string
  sourceLabel: string
  sourceUrl: string
  qualityLabel: string
  relation: string
  claimLabel: string
  sourceId: number
  sourceType: string
  reliabilityPercent: number | null
  reliabilityLabel: string
  reliabilityReasons: string[]
  locatorText: string
  snapshotAvailable: boolean
  contentHash: string
}

// 行尾 Evidence 引用（后端 render_key_claims 会追加 "Evidence: 25, 26"）
const EVIDENCE_SUFFIX = /\s*(?:Evidence|证据)\s*[:：]\s*([0-9,\s、]+)\s*$/
const INLINE_PATTERN = /(\*\*[^*]+\*\*|`[^`]+`)/g
const BULLET_PATTERN = /^[-*]\s+(.*)$/

export type MarkdownInline =
  | { kind: 'text'; text: string }
  | { kind: 'strong'; text: string }
  | { kind: 'code'; text: string }

export type MarkdownListItem = {
  inlines: MarkdownInline[]
  citations: number[]
}

export type MarkdownBlock =
  | { kind: 'paragraph'; inlines: MarkdownInline[]; citations: number[] }
  | { kind: 'list'; items: MarkdownListItem[] }

export function splitCitations(line: string): { text: string; citations: number[] } {
  const match = line.match(EVIDENCE_SUFFIX)
  if (!match || match.index === undefined) {
    return { text: line, citations: [] }
  }
  const citations = match[1]
    .split(/[,\s、]+/)
    .map((value) => Number.parseInt(value, 10))
    .filter((value) => Number.isFinite(value) && value > 0)
  return { text: line.slice(0, match.index).trim(), citations }
}

export function parseMarkdownInlines(text: string): MarkdownInline[] {
  if (!text) return []
  const tokens: MarkdownInline[] = []
  let lastIndex = 0
  let match: RegExpExecArray | null
  INLINE_PATTERN.lastIndex = 0
  while ((match = INLINE_PATTERN.exec(text)) !== null) {
    if (match.index > lastIndex) {
      tokens.push({ kind: 'text', text: text.slice(lastIndex, match.index) })
    }
    const raw = match[0]
    if (raw.startsWith('**')) {
      tokens.push({ kind: 'strong', text: raw.slice(2, -2) })
    } else {
      tokens.push({ kind: 'code', text: raw.slice(1, -1) })
    }
    lastIndex = match.index + raw.length
  }
  if (lastIndex < text.length) {
    tokens.push({ kind: 'text', text: text.slice(lastIndex) })
  }
  return tokens
}

// 将章节 Markdown 解析为结构化块（段落 / 列表），行尾 Evidence 引用单独抽出，
// 供模板渲染成可点击的引用徽章，而不是生文本。
export function renderMarkdownBlocks(markdown: string): MarkdownBlock[] {
  const blocks: MarkdownBlock[] = []
  let pendingItems: MarkdownListItem[] | null = null

  const flushList = () => {
    if (pendingItems && pendingItems.length) {
      blocks.push({ kind: 'list', items: pendingItems })
    }
    pendingItems = null
  }

  for (const rawLine of (markdown || '').split(/\r?\n/)) {
    const line = rawLine.trim()
    if (!line) {
      flushList()
      continue
    }
    const bulletMatch = line.match(BULLET_PATTERN)
    if (bulletMatch) {
      pendingItems = pendingItems ?? []
      const { text, citations } = splitCitations(bulletMatch[1])
      pendingItems.push({ inlines: parseMarkdownInlines(text), citations })
      continue
    }
    flushList()
    const { text, citations } = splitCitations(line)
    blocks.push({ kind: 'paragraph', inlines: parseMarkdownInlines(text), citations })
  }
  flushList()
  return blocks
}

const REASON_LABELS: Record<string, string> = {
  initial_workflow: '初始生成',
  after_review: '审核后生成',
  manual_regenerate: '手动再生成',
}

function generationReason(report: Partial<ReportOut>): string {
  const snapshot = report.input_snapshot as { report_generation?: { reason?: string } } | undefined
  return snapshot?.report_generation?.reason || 'initial_workflow'
}

export function buildReportVersionItems(reports: ReportOut[]): ReportVersionItem[] {
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

export function selectNewestReportVersion(reports: ReportOut[]): number | null {
  if (!reports.length) return null
  return Math.max(...reports.map((report) => report.version))
}

const RELIABILITY_LABELS: Record<string, string> = {
  high: '高',
  medium: '中',
  low: '低',
}

export function reliabilityLabelZh(label: string | null | undefined): string {
  return label ? RELIABILITY_LABELS[label] || label : ''
}

function formatLocatorText(locator: Record<string, unknown> | null | undefined): string {
  if (!locator || typeof locator !== 'object' || Array.isArray(locator)) return ''
  const entries = Object.entries(locator).filter(([, value]) => value !== null && value !== undefined && value !== '')
  return entries.map(([key, value]) => `${key}: ${String(value)}`).join(' · ')
}

export function buildReportSectionEvidenceItems(section: Partial<ReportSectionOut>): ReportSectionEvidenceItem[] {
  return [...(section.evidence ?? [])]
    .sort((a, b) => String(a.id).localeCompare(String(b.id)))
    .map((evidence) => {
      const claimCount = evidence.claim_ids?.length ?? 0
      const reliabilityLevel = reliabilityLabelZh(evidence.reliability_level)
      return {
        id: evidence.id,
        quote: evidence.quote || '',
        sourceLabel: evidence.source_title || evidence.publisher || String(evidence.source_id),
        sourceUrl: evidence.source_url || '',
        qualityLabel: `${Math.round((evidence.quality_score ?? 0) * 100)}%`,
        relation: evidence.relation || 'supports',
        claimLabel: `${claimCount} ${claimCount === 1 ? 'Claim' : 'Claims'}`,
        sourceId: evidence.source_id,
        sourceType: evidence.source_type || '',
        reliabilityPercent: evidence.reliability_score != null ? Math.round(evidence.reliability_score * 100) : null,
        reliabilityLabel: reliabilityLevel,
        reliabilityReasons: evidence.reliability_reasons || [],
        locatorText: formatLocatorText(evidence.locator),
        snapshotAvailable: Boolean(evidence.snapshot_available),
        contentHash: evidence.content_hash || '',
      }
    })
}

export function buildPostReviewReportUpdateState(reports: ReportOut[], selectedVersion: number | null = null): PostReviewReportUpdateState {
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
