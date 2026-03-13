import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', component: () => import('../pages/LandingPage.vue') },
  { path: '/login', component: () => import('../pages/LoginPage.vue') },
  { path: '/profile', redirect: '/settings?tab=appearance' },
  { path: '/projects', component: () => import('../pages/ProjectsPage.vue'), meta: { breadcrumb: [{ to: '/projects', labelKey: 'nav.projects' }] } },
  {
    path: '/projects/:projectId',
    component: () => import('../pages/ProjectDetailPage.vue'),
    meta: {
      breadcrumb: [
        { to: '/projects', labelKey: 'nav.projects' },
        { label: ({ params }) => `Project #${params.projectId}` },
      ],
    },
  },
  {
    path: '/projects/:projectId/stakeholders',
    component: () => import('../pages/StakeholdersPage.vue'),
    meta: {
      breadcrumb: [
        { to: '/projects', labelKey: 'nav.projects' },
        { to: ({ params }) => `/projects/${params.projectId}`, label: ({ params }) => `Project #${params.projectId}` },
        { labelKey: 'stakeholders.title' },
      ],
    },
  },
  { path: '/sessions', component: () => import('../pages/SessionsPage.vue'), meta: { breadcrumb: [{ to: '/sessions', labelKey: 'nav.sessions' }] } },
  {
    path: '/sessions/:sessionId/live',
    component: () => import('../pages/SessionLiveView.vue'),
    meta: {
      breadcrumb: [
        { to: '/sessions', labelKey: 'nav.sessions' },
        { label: ({ params }) => `Session #${params.sessionId}` },
        { labelKey: 'nav.liveView' },
      ],
    },
  },
  {
    path: '/sessions/:sessionId/analytics',
    component: () => import('../pages/AnalyticsDashboard.vue'),
    meta: {
      breadcrumb: [
        { to: '/sessions', labelKey: 'nav.sessions' },
        { to: ({ params }) => `/sessions/${params.sessionId}/live`, label: ({ params }) => `Session #${params.sessionId}` },
        { labelKey: 'nav.analytics' },
      ],
    },
  },
  { path: '/settings', component: () => import('../pages/SettingsPage.vue'), meta: { breadcrumb: [{ to: '/settings', labelKey: 'nav.settings' }] } },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
