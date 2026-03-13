export function resolveBreadcrumbs(route, t) {
  const entries = route?.meta?.breadcrumb || []
  return entries
    .map((entry, idx) => {
      const label = resolveLabel(entry, route, t)
      if (!label) return null

      return {
        key: `${route.path}-${idx}`,
        label,
        to: resolveTo(entry, route),
      }
    })
    .filter(Boolean)
}

function resolveLabel(entry, route, t) {
  if (entry.labelKey) return t(entry.labelKey)
  if (typeof entry.label === 'function') return entry.label(route)
  return entry.label ?? null
}

function resolveTo(entry, route) {
  if (!entry.to) return null
  if (typeof entry.to === 'function') return entry.to(route)
  return entry.to
}
