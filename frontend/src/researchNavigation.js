export function nextPageAfterReview(taskDetail, decision = '') {
  if (decision === 'continue_research') return 'run'
  const hasReport = Array.isArray(taskDetail?.reports) && taskDetail.reports.length > 0
  if (taskDetail?.task?.status === 'completed' && hasReport) return 'report'
  return 'review'
}

export function nextPageAfterTaskRefresh(taskDetail, currentPage = 'run') {
  const hasReport = Array.isArray(taskDetail?.reports) && taskDetail.reports.length > 0
  if (taskDetail?.task?.status === 'completed' && hasReport) return 'report'
  return currentPage
}
