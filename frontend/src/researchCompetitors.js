export function resolveWorkspaceId(value = '', fallback = '') {
  const explicit = String(value || '').trim()
  if (explicit) return explicit
  const configured = String(fallback || '').trim()
  return configured || 'default'
}

export function buildScopedRequestHeaders(headers = {}, scope = {}) {
  const result = {}
  const entries = headers instanceof Headers
    ? Array.from(headers.entries())
    : Array.isArray(headers)
      ? headers
      : Object.entries(headers || {})

  entries.forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      result[key] = String(value)
    }
  })

  const hasHeader = (name) => Object.keys(result).some((key) => key.toLowerCase() === name.toLowerCase())
  const workspaceId = String(scope.workspaceId || '').trim()
  const userId = String(scope.userId || '').trim()
  if (workspaceId && !hasHeader('X-Workspace-Id')) {
    result['X-Workspace-Id'] = workspaceId
  }
  if (userId && !hasHeader('X-User-Id')) {
    result['X-User-Id'] = userId
  }

  return result
}

export function buildCompetitorRows(profiles, fallbackRows) {
  if (!profiles?.length) return fallbackRows
  return profiles.map((profile) => {
    const sourceCount = profile.source_count ?? profile.source_urls?.length ?? 0
    return {
      name: profile.name,
      category: profile.category || 'general',
      reports: profile.report_count ?? 0,
      verified: profile.verified_claim_count ?? 0,
      conflicts: profile.risky_claim_count ?? 0,
      sourceCount,
      update: `${sourceCount} 个常用来源 · ${profile.task_count ?? 0} 个关联任务`,
    }
  })
}

export function buildCompetitorReuseItems(scope) {
  const reusedProfiles = scope?.competitor_profile_reuse
  if (!Array.isArray(reusedProfiles)) return []
  return reusedProfiles
    .filter((profile) => profile && Array.isArray(profile.source_urls))
    .map((profile) => {
      const sources = profile.source_urls.filter((source) => source?.url)
      const sourceCount = profile.source_count ?? sources.length
      return {
        id: profile.profile_id || profile.name,
        name: profile.name || 'Unknown competitor',
        sourceCount,
        sourceCountLabel: `${sourceCount} 个来源`,
        sourceLabels: sources.map((source) => source.label || source.source_type || source.url).join(', '),
      }
    })
}
