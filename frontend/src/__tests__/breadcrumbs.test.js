import { describe, it, expect } from 'vitest'
import { resolveBreadcrumbs } from '../utils/breadcrumbs'

describe('resolveBreadcrumbs', () => {
  const t = (key) => key

  it('resolves label keys and function labels', () => {
    const route = {
      path: '/sessions/42/live',
      params: { sessionId: '42' },
      meta: {
        breadcrumb: [
          { to: '/sessions', labelKey: 'nav.sessions' },
          { label: ({ params }) => `Session #${params.sessionId}` },
          { labelKey: 'nav.liveView' },
        ],
      },
    }

    expect(resolveBreadcrumbs(route, t)).toEqual([
      { key: '/sessions/42/live-0', label: 'nav.sessions', to: '/sessions' },
      { key: '/sessions/42/live-1', label: 'Session #42', to: null },
      { key: '/sessions/42/live-2', label: 'nav.liveView', to: null },
    ])
  })

  it('resolves dynamic links and ignores empty labels', () => {
    const route = {
      path: '/projects/9/stakeholders',
      params: { projectId: '9' },
      meta: {
        breadcrumb: [
          { to: '/projects', labelKey: 'nav.projects' },
          { to: ({ params }) => `/projects/${params.projectId}`, label: ({ params }) => `Project #${params.projectId}` },
          { label: '' },
        ],
      },
    }

    expect(resolveBreadcrumbs(route, t)).toEqual([
      { key: '/projects/9/stakeholders-0', label: 'nav.projects', to: '/projects' },
      { key: '/projects/9/stakeholders-1', label: 'Project #9', to: '/projects/9' },
    ])
  })
})
