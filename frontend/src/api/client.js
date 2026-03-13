import axios from 'axios'
import { useAuthStore } from '../stores/auth'

// Dev: Vite proxy handles /api/ → localhost:8000 (no env var needed)
// Docker: nginx proxies /api/ → backend container
// Production (Vercel): rewrites /api/ → VPS backend
export const API_BASE = import.meta.env.VITE_API_BASE || window.location.origin

const api = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
})

// Inject JWT on all API requests (useAuthStore called lazily inside interceptor
// to avoid Pinia initialization order issues)
api.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.token) {
    config.headers['Authorization'] = `Bearer ${auth.token}`
  }
  return config
})

// Projects
export const getProjects = () => api.get('/api/projects/')
export const getProject = (id) => api.get(`/api/projects/${id}`)
export const createProject = (data) => api.post('/api/projects/', data)
export const updateProject = (id, data) => api.put(`/api/projects/${id}`, data)
export const seedDemoProject = () => api.post('/api/projects/seed-demo')

// Stakeholders
export const getStakeholders = (projectId) => api.get(`/api/projects/${projectId}/stakeholders`)
export const createStakeholder = (projectId, data) => api.post(`/api/projects/${projectId}/stakeholders`, data)
export const updateStakeholder = (projectId, id, data) => api.put(`/api/projects/${projectId}/stakeholders/${id}`, data)
export const deleteStakeholder = (projectId, id) => api.delete(`/api/projects/${projectId}/stakeholders/${id}`)
export const getEdges = (projectId) => api.get(`/api/projects/${projectId}/edges`)

// Sessions — CRUD
export const getSessions = (projectId) => api.get(`/api/sessions/?project_id=${projectId}`)
export const getSession = (id) => api.get(`/api/sessions/${id}`)
export const getMessages = (sessionId) => api.get(`/api/sessions/${sessionId}/messages`)
export const createSession = (data) => api.post('/api/sessions/', data)
export const deleteSession = (id) => api.delete(`/api/sessions/${id}`)

// Sessions — Execution
export const runSession = (sessionId, config = {}) =>
  api.post(`/api/sessions/${sessionId}/run`, config)

export const stopSession = (sessionId) =>
  api.post(`/api/sessions/${sessionId}/stop`)

export const pauseSession = (sessionId) =>
  api.post(`/api/sessions/${sessionId}/pause`)

export const resumeSession = (sessionId) =>
  api.post(`/api/sessions/${sessionId}/resume`)

export const continueSession = (sessionId, data) =>
  api.post(`/api/sessions/${sessionId}/continue`, data)

export const recoverSession = (sessionId, additionalRounds = 5) =>
  api.post(`/api/sessions/${sessionId}/recover`, { additional_rounds: additionalRounds })

export const injectMessage = (sessionId, content, asModerator = false) =>
  api.post(`/api/sessions/${sessionId}/inject`, { content, as_moderator: asModerator })

export const getAnalytics = (sessionId) =>
  api.get(`/api/sessions/${sessionId}/analytics`)

// SSE stream helper (#130: use short-lived ticket instead of raw JWT in URL)
export async function createSessionStream(sessionId) {
  const url = new URL(`${API_BASE}/api/sessions/${sessionId}/stream`)
  try {
    // POST /stream-ticket with Authorization header to get a one-time token
    const resp = await api.post(`/api/sessions/${sessionId}/stream-ticket`)
    url.searchParams.set('ticket', resp.data.ticket)
  } catch {
    // If ticket endpoint is unavailable (dev mode without auth), fall back silently
  }
  return new EventSource(url.toString())
}

// LLM Settings
export const getSettingsProfiles = () => api.get('/api/settings/')
export const getActiveSettings = () => api.get('/api/settings/active')
export const createSettingsProfile = (data) => api.post('/api/settings/', data)
export const updateSettingsProfile = (name, data) => api.put(`/api/settings/${name}`, data)
export const activateProfile = (name) => api.post(`/api/settings/${name}/activate`)
export const getAvailableVoices = () => api.get('/api/settings/voices')
export const getProviderPresets = () => api.get('/api/settings/providers')

// Provider management
export const getProviderCatalog = () => api.get('/api/providers/')
export const getProviderKeys = () => api.get('/api/providers/keys')
export const saveProviderKey = (data) => api.post('/api/providers/keys', data)
export const removeProviderKey = (providerId) => api.delete(`/api/providers/keys/${providerId}`)
export const testProviderConnection = (providerId) => api.post(`/api/providers/keys/${providerId}/test`)
export const getProviderModels = (providerId) => api.get(`/api/providers/${providerId}/models`)

// Model registry
export const getModelRegistry = () => api.get('/api/settings/models/registry')
export const refreshModels = () => api.post('/api/settings/models/refresh')
export const toggleModel = (providerId, modelId) => api.put(`/api/settings/models/${providerId}/${modelId}/toggle`)
export const setDefaultModel = (data) => api.put('/api/settings/defaults', data)

export default api
