import type { CompetitorProfileOut } from './api'

export function resolveWorkspaceId(value?: string, fallback?: string): string

export function buildScopedRequestHeaders(
  headers?: HeadersInit,
  scope?: { workspaceId?: string; userId?: string },
): Record<string, string>

export type CompetitorRow = {
  name: string
  category: string
  reports: number
  verified: number
  conflicts: number
  sourceCount?: number
  update: string
}

export function buildCompetitorRows(profiles: CompetitorProfileOut[], fallbackRows: CompetitorRow[]): CompetitorRow[]

export type CompetitorReuseItem = {
  id: string
  name: string
  sourceCount: number
  sourceCountLabel: string
  sourceLabels: string
}

export function buildCompetitorReuseItems(scope: Record<string, unknown>): CompetitorReuseItem[]
