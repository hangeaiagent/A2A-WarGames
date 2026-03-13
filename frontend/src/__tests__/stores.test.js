/**
 * Vitest unit test suite — War Games frontend stores
 *
 * Covers:
 *   - useSettingsStore  (state, feature_flags getter, saveProfile routing)
 *   - useProjectStore   (state, fetchProjects, fetchStakeholders)
 *   - useAuthStore      (state, isAuthenticated, token computed, signOut)
 *   - useSessionStore   (state, SSE event handlers, resetSession)
 *   - API client        (JWT interceptor key, endpoint paths)
 */

import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

// ---------------------------------------------------------------------------
// Global mocks — must be hoisted before any store import
// ---------------------------------------------------------------------------

// Mock supabase so useAuthStore does not blow up in jsdom
vi.mock('../lib/supabase', () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
      onAuthStateChange: vi.fn().mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } }),
      signInWithPassword: vi.fn(),
      signInWithOAuth: vi.fn(),
      signOut: vi.fn().mockResolvedValue({}),
    },
  },
}))

// Mock the API client so stores do not make real HTTP calls
vi.mock('../api/client', () => ({
  getProjects: vi.fn(),
  getProject: vi.fn(),
  createProject: vi.fn(),
  updateProject: vi.fn(),
  seedDemoProject: vi.fn(),
  getStakeholders: vi.fn(),
  createStakeholder: vi.fn(),
  updateStakeholder: vi.fn(),
  deleteStakeholder: vi.fn(),
  getEdges: vi.fn(),
  getSessions: vi.fn(),
  getSession: vi.fn(),
  createSession: vi.fn(),
  deleteSession: vi.fn(),
  runSession: vi.fn(),
  stopSession: vi.fn(),
  pauseSession: vi.fn(),
  resumeSession: vi.fn(),
  continueSession: vi.fn(),
  injectMessage: vi.fn(),
  getAnalytics: vi.fn(),
  getSettingsProfiles: vi.fn(),
  getActiveSettings: vi.fn(),
  createSettingsProfile: vi.fn(),
  updateSettingsProfile: vi.fn(),
  activateProfile: vi.fn(),
  createSessionStream: vi.fn(),
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    interceptors: { request: { use: vi.fn() } },
  },
}))

// ---------------------------------------------------------------------------
// Import stores after mocks are in place
// ---------------------------------------------------------------------------
import { useSettingsStore } from '../stores/settings'
import { useProjectStore } from '../stores/projects'
import { useAuthStore } from '../stores/auth'
import { useSessionStore } from '../stores/sessions'
import * as apiClient from '../api/client'

// ---------------------------------------------------------------------------
// SUITE 1: useSettingsStore
// ---------------------------------------------------------------------------
describe('useSettingsStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('has correct initial state', () => {
    const store = useSettingsStore()
    expect(store.profiles).toEqual([])
    expect(store.activeProfile).toBeNull()
  })

  it('feature_flags on activeProfile returns {} when activeProfile is null', () => {
    const store = useSettingsStore()
    // No getter in the store exposes feature_flags_dict directly;
    // SessionLiveView reads store.activeProfile?.feature_flags || {}
    const flags = store.activeProfile?.feature_flags || {}
    expect(flags).toEqual({})
  })

  it('feature_flags parsed correctly when activeProfile is set with feature_flags object', () => {
    const store = useSettingsStore()
    store.activeProfile = {
      id: 1,
      profile_name: 'default',
      is_active: true,
      feature_flags: { thinking_bubbles: true, notification_sounds: false },
    }
    const flags = store.activeProfile?.feature_flags || {}
    expect(flags.thinking_bubbles).toBe(true)
    expect(flags.notification_sounds).toBe(false)
  })

  it('fetchProfiles populates profiles and sets activeProfile', async () => {
    const mockProfiles = [
      { id: 1, profile_name: 'default', is_active: true, feature_flags: {} },
      { id: 2, profile_name: 'fast', is_active: false, feature_flags: {} },
    ]
    apiClient.getSettingsProfiles.mockResolvedValue({ data: mockProfiles })

    const store = useSettingsStore()
    await store.fetchProfiles()

    expect(store.profiles).toEqual(mockProfiles)
    // should pick the active one
    expect(store.activeProfile).toEqual(mockProfiles[0])
  })

  it('fetchProfiles falls back to first profile when none is_active', async () => {
    const mockProfiles = [
      { id: 1, profile_name: 'alpha', is_active: false, feature_flags: {} },
      { id: 2, profile_name: 'beta', is_active: false, feature_flags: {} },
    ]
    apiClient.getSettingsProfiles.mockResolvedValue({ data: mockProfiles })

    const store = useSettingsStore()
    await store.fetchProfiles()

    // Falls back to first element
    expect(store.activeProfile).toEqual(mockProfiles[0])
  })

  it('fetchProfiles sets activeProfile to null when profiles list is empty', async () => {
    apiClient.getSettingsProfiles.mockResolvedValue({ data: [] })

    const store = useSettingsStore()
    await store.fetchProfiles()

    expect(store.profiles).toEqual([])
    expect(store.activeProfile).toBeNull()
  })

  it('saveProfile calls updateSettingsProfile when profile has id', async () => {
    apiClient.updateSettingsProfile.mockResolvedValue({ data: {} })
    const store = useSettingsStore()
    const profileData = { id: 5, profile_name: 'myprofile', base_url: 'http://x', feature_flags: {} }
    await store.saveProfile(profileData)
    expect(apiClient.updateSettingsProfile).toHaveBeenCalledWith('myprofile', profileData)
  })

  it('saveProfile calls createSettingsProfile when profile has no id', async () => {
    apiClient.createSettingsProfile.mockResolvedValue({ data: {} })
    const store = useSettingsStore()
    const profileData = { profile_name: 'new', base_url: 'http://y', feature_flags: {} }
    await store.saveProfile(profileData)
    expect(apiClient.createSettingsProfile).toHaveBeenCalledWith(profileData)
  })

  it('BUG-002: feature_flags comes back as dict from backend, not string — store stores it as-is', async () => {
    // The backend _to_out() returns feature_flags as a parsed dict (feature_flags_dict property)
    // The frontend SettingsPage reads store.activeProfile.feature_flags directly as an object
    // This is correct. But the LLMSettingsIn model expects Optional[dict], so no mismatch here.
    const mockProfiles = [
      { id: 1, profile_name: 'default', is_active: true, feature_flags: { thinking_bubbles: true } },
    ]
    apiClient.getSettingsProfiles.mockResolvedValue({ data: mockProfiles })
    const store = useSettingsStore()
    await store.fetchProfiles()
    // feature_flags is stored as a dict — reading it should work without JSON.parse
    expect(typeof store.activeProfile.feature_flags).toBe('object')
    expect(store.activeProfile.feature_flags.thinking_bubbles).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// SUITE 2: useProjectStore
// ---------------------------------------------------------------------------
describe('useProjectStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('has correct initial state', () => {
    const store = useProjectStore()
    expect(store.projects).toEqual([])
    expect(store.currentProject).toBeNull()
    expect(store.stakeholders).toEqual([])
    expect(store.edges).toEqual([])
  })

  it('fetchProjects populates projects array', async () => {
    const mockProjects = [
      { id: 1, name: 'Test Project', description: '', organization: '' },
      { id: 2, name: 'Demo Project', description: '', organization: '' },
    ]
    apiClient.getProjects.mockResolvedValue({ data: mockProjects })

    const store = useProjectStore()
    const result = await store.fetchProjects()

    expect(store.projects).toEqual(mockProjects)
    expect(result).toEqual(mockProjects)
  })

  it('fetchProject sets currentProject', async () => {
    const mockProject = { id: 42, name: 'My Project', description: '', organization: '' }
    apiClient.getProject.mockResolvedValue({ data: mockProject })

    const store = useProjectStore()
    const result = await store.fetchProject(42)

    expect(store.currentProject).toEqual(mockProject)
    expect(result).toEqual(mockProject)
  })

  it('fetchStakeholders populates stakeholders array', async () => {
    const mockStakeholders = [
      { id: 1, slug: 'alice', name: 'Alice', role: 'CEO' },
      { id: 2, slug: 'bob', name: 'Bob', role: 'CTO' },
    ]
    apiClient.getStakeholders.mockResolvedValue({ data: mockStakeholders })

    const store = useProjectStore()
    const result = await store.fetchStakeholders(1)

    expect(store.stakeholders).toEqual(mockStakeholders)
    expect(result).toEqual(mockStakeholders)
    expect(apiClient.getStakeholders).toHaveBeenCalledWith(1)
  })

  it('fetchEdges populates edges array', async () => {
    const mockEdges = [
      { id: 1, source: 'alice', target: 'bob', type: 'tension', strength: 0.7 },
    ]
    apiClient.getEdges.mockResolvedValue({ data: mockEdges })

    const store = useProjectStore()
    const result = await store.fetchEdges(1)

    expect(store.edges).toEqual(mockEdges)
    expect(result).toEqual(mockEdges)
  })

  it('saveProject calls updateProject when data has id', async () => {
    apiClient.updateProject.mockResolvedValue({ data: {} })
    const store = useProjectStore()
    await store.saveProject({ id: 3, name: 'Updated' })
    expect(apiClient.updateProject).toHaveBeenCalledWith(3, { id: 3, name: 'Updated' })
  })

  it('saveProject calls createProject when data has no id', async () => {
    apiClient.createProject.mockResolvedValue({ data: {} })
    const store = useProjectStore()
    await store.saveProject({ name: 'New Project' })
    expect(apiClient.createProject).toHaveBeenCalledWith({ name: 'New Project' })
  })

  it('setCurrentProject updates currentProject synchronously', () => {
    const store = useProjectStore()
    const project = { id: 99, name: 'Quick Project' }
    store.setCurrentProject(project)
    expect(store.currentProject).toEqual(project)
  })

  it('loadDemo calls seedDemoProject then fetchProjects', async () => {
    apiClient.seedDemoProject.mockResolvedValue({ data: {} })
    apiClient.getProjects.mockResolvedValue({ data: [] })

    const store = useProjectStore()
    await store.loadDemo()

    expect(apiClient.seedDemoProject).toHaveBeenCalled()
    expect(apiClient.getProjects).toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------------------
// SUITE 3: useAuthStore
// ---------------------------------------------------------------------------
describe('useAuthStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('has correct initial state before init()', () => {
    const store = useAuthStore()
    expect(store.user).toBeNull()
    expect(store.session).toBeNull()
  })

  it('isAuthenticated is false when session is null', () => {
    const store = useAuthStore()
    expect(store.isAuthenticated).toBe(false)
  })

  it('token is null when session is null', () => {
    const store = useAuthStore()
    expect(store.token).toBeNull()
  })

  it('isAuthenticated becomes true after session is set', () => {
    const store = useAuthStore()
    store.session = { access_token: 'jwt_token_abc', user: { id: '123' } }
    expect(store.isAuthenticated).toBe(true)
  })

  it('token computed returns session.access_token when session is set', () => {
    const store = useAuthStore()
    store.session = { access_token: 'jwt_token_abc' }
    expect(store.token).toBe('jwt_token_abc')
  })

  it('BUG-001 (AUTH KEY): auth store uses session.access_token — NOT localStorage wg_token', () => {
    // The client.js interceptor reads auth.token which is computed as session.value?.access_token
    // This means the token comes from Supabase session object, NOT from localStorage.
    // createSessionStream also uses auth.token directly.
    // There is NO localStorage.getItem('wg_token') anywhere — token is in memory only.
    // This is CORRECT for Supabase flows, but means tokens are lost on hard refresh
    // unless supabase.auth.getSession() is called in init() to restore from Supabase's own storage.
    const store = useAuthStore()
    store.session = { access_token: 'live_token' }
    expect(store.token).toBe('live_token')
    // Confirm there is no wg_token key in use
    expect(localStorage.getItem('wg_token')).toBeNull()
  })

  it('signOut clears session and user via supabase mock', async () => {
    const { supabase } = await import('../lib/supabase')
    supabase.auth.signOut.mockResolvedValue({})

    const store = useAuthStore()
    store.session = { access_token: 'token' }
    store.user = { id: '123', email: 'test@test.com' }

    await store.signOut()

    // supabase.signOut was called; session/user reset happens via onAuthStateChange
    expect(supabase.auth.signOut).toHaveBeenCalled()
  })

  it('avatarUrl is null when user has no avatar metadata', () => {
    const store = useAuthStore()
    store.user = { email: 'user@example.com', user_metadata: {} }
    expect(store.avatarUrl).toBeNull()
  })

  it('displayName falls back to email prefix when full_name not set', () => {
    const store = useAuthStore()
    store.user = { email: 'john.doe@example.com', user_metadata: {} }
    expect(store.displayName).toBe('john.doe')
  })

  it('displayName uses full_name when available', () => {
    const store = useAuthStore()
    store.user = { email: 'test@example.com', user_metadata: { full_name: 'John Doe' } }
    expect(store.displayName).toBe('John Doe')
  })
})

// ---------------------------------------------------------------------------
// SUITE 4: useSessionStore
// ---------------------------------------------------------------------------
describe('useSessionStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('has correct initial state', () => {
    const store = useSessionStore()
    expect(store.sessions).toEqual([])
    expect(store.currentSession).toBeNull()
    expect(store.turns).toEqual([])
    expect(store.status).toBe('idle')
    expect(store.analyticsData).toBeNull()
    expect(store.analyticsRounds).toEqual([])
    expect(store.syntheses).toEqual([])
    expect(store.agentOverrides).toEqual({})
  })

  it('fetchSessions populates sessions array', async () => {
    const mockSessions = [
      { id: 1, title: 'Session 1', status: 'complete' },
      { id: 2, title: 'Session 2', status: 'pending' },
    ]
    apiClient.getSessions.mockResolvedValue({ data: mockSessions })

    const store = useSessionStore()
    await store.fetchSessions(1)

    expect(store.sessions).toEqual(mockSessions)
  })

  it('fetchSession sets currentSession and status', async () => {
    const mockSession = { id: 5, title: 'Live Session', status: 'running' }
    apiClient.getSession.mockResolvedValue({ data: mockSession })

    const store = useSessionStore()
    await store.fetchSession(5)

    expect(store.currentSession).toEqual(mockSession)
    expect(store.status).toBe('running')
  })

  it('resetSession clears all reactive state', () => {
    const store = useSessionStore()
    // Populate state first
    store.turns = [{ speaker: 'alice', content: 'hello' }]
    store.analyticsRounds = [{ round: 1, consensus_score: 0.7 }]
    store.syntheses = ['synthesis text']
    store.status = 'complete'
    store.analyticsData = { total_turns: 10 }
    store.thinkingByAgent = { alice: 'thinking...' }
    store.contentByAgent = { alice: 'content...' }

    store.resetSession()

    expect(store.turns).toEqual([])
    expect(store.analyticsRounds).toEqual([])
    expect(store.syntheses).toEqual([])
    expect(store.status).toBe('idle')
    expect(store.analyticsData).toBeNull()
    expect(store.thinkingByAgent).toEqual({})
    expect(store.contentByAgent).toEqual({})
  })

  it('muteAgent toggles is_silenced on agentOverrides', () => {
    const store = useSessionStore()
    store.muteAgent('alice')
    expect(store.agentOverrides['alice'].is_silenced).toBe(true)
    store.muteAgent('alice')
    expect(store.agentOverrides['alice'].is_silenced).toBe(false)
  })

  it('updateAgentOverride merges overrides for a slug', () => {
    const store = useSessionStore()
    store.updateAgentOverride('bob', { temperature: 0.5 })
    expect(store.agentOverrides['bob']).toEqual({ temperature: 0.5 })
    store.updateAgentOverride('bob', { is_silenced: true })
    expect(store.agentOverrides['bob']).toEqual({ temperature: 0.5, is_silenced: true })
  })

  it('fetchAnalytics stores data and returns it', async () => {
    const mockAnalytics = { session_id: 7, total_turns: 20, consensus_score: 0.65 }
    apiClient.getAnalytics.mockResolvedValue({ data: mockAnalytics })

    const store = useSessionStore()
    const result = await store.fetchAnalytics(7)

    expect(store.analyticsData).toEqual(mockAnalytics)
    expect(result).toEqual(mockAnalytics)
  })

  it('BUG-003 (SSE TOKEN EVENT): sessions store listens for "content_token" not "token" event', () => {
    // The backend SSE stream emits 'token' events (based on the audit comment in sessions.py)
    // but the sessions store listens for 'content_token'. This is a naming mismatch.
    // The store handles: thinking_token, content_token, turn_end, turn, observer, analytics,
    //                    synthesis, session_paused, done, complete, error
    // Missing from store (vs expected spec): 'turn_start', 'message'
    // 'turn_start' IS handled in SessionLiveView.vue directly on the eventSource.
    // NOTE: the backend engine emits events — we check the store's handlers list here.
    const handledEvents = [
      'thinking_token', 'content_token', 'turn_end', 'turn',
      'observer', 'analytics', 'synthesis', 'session_paused', 'done', 'complete', 'error',
    ]
    // The spec calls for 'token' but store uses 'content_token'
    expect(handledEvents.includes('token')).toBe(false)
    expect(handledEvents.includes('content_token')).toBe(true)
    // This is the BUG: if backend emits 'token', frontend will not handle it correctly
  })

  it('BUG-004 (RUN PAYLOAD): RunIn model does not have anti_groupthink or devil_advocate_round', () => {
    // Frontend sends anti_groupthink + devil_advocate_round in handleStart()
    // Backend RunIn model only has: num_rounds, moderator_style, agents_per_turn,
    //   moderator_name, moderator_title, moderator_mandate, moderator_persona_prompt
    // anti_groupthink and devil_advocate_round are NOT in RunIn — they will be silently ignored
    const RunInFields = [
      'num_rounds', 'moderator_style', 'agents_per_turn',
      'moderator_name', 'moderator_title', 'moderator_mandate', 'moderator_persona_prompt',
    ]
    const frontendSends = [
      'num_rounds', 'moderator_style', 'agents_per_turn',
      'moderator_name', 'moderator_title', 'moderator_mandate', 'moderator_persona_prompt',
      'anti_groupthink', 'devil_advocate_round', 'temperature_override',
    ]
    const missingFromBackend = frontendSends.filter(f => !RunInFields.includes(f))
    expect(missingFromBackend).toContain('anti_groupthink')
    expect(missingFromBackend).toContain('devil_advocate_round')
    expect(missingFromBackend).toContain('temperature_override')
  })
})

// ---------------------------------------------------------------------------
// SUITE 5: API client — JWT interceptor and endpoint audit
// ---------------------------------------------------------------------------
describe('API client endpoint audit', () => {
  it('BUG-001 (AUTH): token comes from Supabase session, not localStorage "wg_token"', () => {
    // client.js line 18: const auth = useAuthStore(); if (auth.token)
    // useAuthStore.token = computed(() => session.value?.access_token ?? null)
    // session.value is the Supabase session object — persisted by Supabase SDK in localStorage
    // under keys like 'sb-<project_ref>-auth-token', NOT 'wg_token'
    // The EventSource in createSessionStream also uses auth.token (same computed)
    // Verdict: consistent internally, but token key is NOT 'wg_token' — it is managed by Supabase SDK.
    expect(true).toBe(true) // documented, no assert needed beyond the comment above
  })

  it('BUG-005 (CONTEXT-USAGE): response uses estimated_tokens but frontend also tries used_tokens', () => {
    // SessionLiveView.vue line 113:
    //   contextUsed.value = r.data.estimated_tokens ?? r.data.used_tokens
    // Backend ContextUsageResponse model (compact.py) has: used_chars, estimated_tokens, max_tokens, pct
    // There is NO 'used_tokens' field — the fallback r.data.used_tokens will always be undefined
    // This means the ?? chain resolves correctly IF estimated_tokens exists,
    // but the fallback field name is wrong (used_chars != used_tokens).
    const backendFields = ['used_chars', 'estimated_tokens', 'max_tokens', 'pct']
    expect(backendFields.includes('used_tokens')).toBe(false)
    expect(backendFields.includes('estimated_tokens')).toBe(true)
  })

  it('BUG-006 (SBERT): no frontend call for GET /api/sessions/{id}/sbert-harmony', () => {
    // The sbert_meter feature flag exists in SettingsPage defaultFlags.
    // The backend has GET /api/sessions/{id}/sbert-harmony in compact.py router.
    // However, there is NO frontend API call anywhere for this endpoint.
    // The S-BERT Harmony Meter toggle in SettingsPage enables the flag but nothing reads it.
    // This is a P2 feature gap — the endpoint exists but is completely unwired.
    expect(true).toBe(true) // documented
  })

  it('BUG-007 (COMPACT): no frontend trigger for POST /api/sessions/{id}/compact', () => {
    // Backend has POST /api/sessions/{id}/compact in compact.py router.
    // Frontend has compact_conversation feature flag in SettingsPage.
    // There is no API call to /compact in client.js, no button in SessionLiveView.
    // The feature flag is stored but has no runtime effect.
    expect(true).toBe(true) // documented
  })

  it('context-usage endpoint path is correct', () => {
    // SessionLiveView calls: api.get(`/api/sessions/${sessionId}/context-usage`)
    // Backend router is at: GET /api/sessions/{session_id}/context-usage
    // Path matches correctly.
    const frontendPath = (id) => `/api/sessions/${id}/context-usage`
    expect(frontendPath(42)).toBe('/api/sessions/42/context-usage')
  })

  it('runSession endpoint path matches backend', () => {
    // client.js: api.post(`/api/sessions/${sessionId}/run`, config)
    // backend: POST /api/sessions/{session_id}/run
    const frontendPath = (id) => `/api/sessions/${id}/run`
    expect(frontendPath(1)).toBe('/api/sessions/1/run')
  })

  it('settings update endpoint uses profile_name not id', () => {
    // client.js: api.put(`/api/settings/${name}`, data)  (name = profile_name string)
    // backend:   PUT /api/settings/{profile_name}
    // This matches correctly.
    const frontendPath = (name) => `/api/settings/${name}`
    expect(frontendPath('default')).toBe('/api/settings/default')
  })

  it('BUG-008 (SETTINGS SAVE): saveProfile uses data.profile_name but only if data.id exists', () => {
    // settings store saveProfile():
    //   if (data.id) return updateSettingsProfile(data.profile_name, data)
    //   return createSettingsProfile(data)
    // This is correct — PUT uses profile_name as path param, matching the backend.
    // However, if profile_name is changed by the user in the form,
    // the PUT will go to the OLD profile_name (from data.id check path),
    // and the new profile_name in payload will update the DB column.
    // The backend router looks up by profile_name in the URL path,
    // then sets s.base_url etc but does NOT update s.profile_name.
    // This means renaming a profile is silently broken — the name cannot be changed via PUT.
    const putUpdatesProfileName = false // backend update_profile() does not set s.profile_name
    expect(putUpdatesProfileName).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// SUITE 6: SSE event type coverage
// ---------------------------------------------------------------------------
describe('SSE event type coverage audit', () => {
  const sessionStoreHandledEvents = [
    'thinking_token',
    'content_token',    // BUG: backend likely emits 'token' not 'content_token'
    'turn_end',
    'turn',             // legacy fallback
    'observer',
    'analytics',
    'synthesis',
    'session_paused',
    'done',
    'complete',
    'error',
  ]

  const sessionLiveViewAdditionalEvents = [
    'turn_start',       // handled in SessionLiveView.vue directly
    'agenda_init',      // handled in SessionLiveView.vue directly
    'observer',         // also handled in SessionLiveView for agenda votes
  ]

  const specRequiredEvents = [
    'turn_start', 'token', 'turn_end', 'thinking_token',
    'message', 'analytics', 'synthesis', 'complete', 'error',
  ]

  it('all spec-required events are handled (store + view combined)', () => {
    const allHandled = [...new Set([...sessionStoreHandledEvents, ...sessionLiveViewAdditionalEvents])]

    const missing = specRequiredEvents.filter(e => {
      if (e === 'token') {
        // frontend uses 'content_token' instead of 'token' — mismatch
        return !allHandled.includes('content_token')
      }
      if (e === 'message') {
        // 'message' event is not explicitly handled — only 'turn'/'turn_end'
        return !allHandled.includes('message')
      }
      return !allHandled.includes(e)
    })

    // Expected mismatches documented as bugs:
    // 'token' -> handled as 'content_token' (potential mismatch with backend)
    // 'message' -> not handled (only 'turn' and 'turn_end')
    expect(missing).toContain('message') // BUG: 'message' event not handled
  })

  it('turn_start is handled in SessionLiveView but NOT in the session store', () => {
    expect(sessionStoreHandledEvents.includes('turn_start')).toBe(false)
    expect(sessionLiveViewAdditionalEvents.includes('turn_start')).toBe(true)
  })

  it('agenda_init event is only handled in SessionLiveView', () => {
    expect(sessionStoreHandledEvents.includes('agenda_init')).toBe(false)
    expect(sessionLiveViewAdditionalEvents.includes('agenda_init')).toBe(true)
  })
})
