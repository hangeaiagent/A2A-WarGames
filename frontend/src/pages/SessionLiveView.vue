<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useSessionStore } from '../stores/sessions'
import { useProjectStore } from '../stores/projects'
import { useSettingsStore } from '../stores/settings'
import { useNotificationSounds } from '../composables/useNotificationSounds'
import AgentPanel from '../components/session/AgentPanel.vue'
import DebateTranscript from '../components/session/DebateTranscript.vue'
import InjectBar from '../components/session/InjectBar.vue'
import ConfigDrawer from '../components/session/ConfigDrawer.vue'
import SessionBottomBar from '../components/session/SessionBottomBar.vue'
import ScaleTransition from '../components/transitions/ScaleTransition.vue'
import WhisperPanel from '../components/session/WhisperPanel.vue'
import ConsensusGauge from '../components/metrics/ConsensusGauge.vue'
import SentimentPanel from '../components/metrics/SentimentPanel.vue'
import RiskTable from '../components/metrics/RiskTable.vue'
import ConsensusTimeline from '../components/metrics/ConsensusTimeline.vue'
import SynthesesPanel from '../components/metrics/SynthesesPanel.vue'
import StatusBadge from '../components/common/StatusBadge.vue'
import Spinner from '../components/common/Spinner.vue'
import AgendaPanel from '../components/AgendaPanel.vue'
import BottomAnalyticsBar from '../components/session/BottomAnalyticsBar.vue'
import api from '../api/client'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const sessionStore = useSessionStore()
const projectStore = useProjectStore()
const settingsStore = useSettingsStore()

const sessionId = computed(() => Number(route.params.sessionId))
const configOpen = ref(false)
const error = ref(null)

// Sidebar collapse state — both panels start collapsed on mobile (< 768px)
const isMobile = () => window.innerWidth < 768
const leftPanelOpen = ref(!isMobile())
const rightPanelOpen = ref(!isMobile())

// Thinking indicator
const thinkingSpeaker = ref(null)

// Context meter
const contextUsed = ref(0)
const contextMax = ref(128000)

// S-BERT harmony meter (BUG-006)
const harmonyScore = ref(null)

// Compact conversation (BUG-007)
const compactLoading = ref(false)

const config = ref({
  num_rounds: 5,
  agents_per_turn: 3,
  moderator_style: 'neutral',
  moderator_name: 'Moderator',
  moderator_title: '',
  moderator_mandate: '',
  moderator_persona_prompt: '',
  anti_groupthink: true,
  devil_advocate_round: 0,
  temperature_override: null,
  context_window_strategy: 'last_2_rounds',
  // CR-011 whisper channel config
  private_thread_limit: 3,
  private_thread_depth: 2,
  private_thread_quota_mode: 'fixed',
})

const participants = ref([])

// Agenda tracking (CR-006)
const agenda = ref({ items: [] })
const emptyTally = () => ({ agree: 0, oppose: 0, neutral: 0, abstain: 0 })

// Build a slug->stakeholder map for transcript
const stakeholderMap = computed(() => {
  const map = {}
  for (const p of participants.value) {
    map[p.slug] = p
  }
  return map
})

// Feature flags
const featureFlags = computed(() => settingsStore.activeProfile?.feature_flags || {})
const contextMeterEnabled = computed(() => featureFlags.value.context_meter ?? true)
const thinkingIndicatorEnabled = computed(() => featureFlags.value.thinking_indicator ?? true)
const sbertMeterEnabled = computed(() => featureFlags.value.sbert_meter ?? false)
const compactConversationEnabled = computed(() => featureFlags.value.compact_conversation ?? false)
const dagVisualizationEnabled = computed(() => featureFlags.value.dag_visualization ?? true)

// Wire notification_sounds feature flag to the composable's enabled state
const sounds = useNotificationSounds()
watch(
  () => featureFlags.value.notification_sounds,
  (val) => sounds.setEnabled(val ?? false),
  { immediate: true }
)

onMounted(async () => {
  sessionStore.resetSession()
  try {
    const session = await sessionStore.fetchSession(sessionId.value)
    if (session.project_id) {
      const stks = await projectStore.fetchStakeholders(session.project_id)
      participants.value = stks.filter(s => (session.participants || []).includes(s.slug))
    }
    // Load historical messages only for sessions that are NOT actively streaming.
    // Running sessions get turns via SSE — pre-loading causes duplication.
    if (['complete', 'failed', 'paused', 'interrupted'].includes(session.status)) {
      try {
        const r = await api.get(`/api/sessions/${sessionId.value}/messages`)
        const msgs = r.data ?? []
        msgs.forEach(msg => sessionStore.turns.push({ ...msg, thinking: '' }))
      } catch {
        // Non-fatal: transcript unavailable
      }
    }
    // Sync status from DB so pause/recover buttons render correctly
    sessionStore.status = session.status
  } catch {
    error.value = t('sessionLive.sessionError')
  }
  // Fetch settings for feature flags
  try {
    await settingsStore.fetchProfiles()
  } catch {
    // Settings may not be available
  }
})

onUnmounted(() => {
  sessionStore.eventSource?.close()
})

async function fetchContextUsage() {
  if (!contextMeterEnabled.value) return
  try {
    const r = await api.get(`/api/sessions/${sessionId.value}/context-usage`)
    contextUsed.value = r.data.estimated_tokens ?? r.data.used_tokens
    contextMax.value = r.data.max_tokens
  } catch {
    // Fallback: estimate from total character count (~4 chars per token)
    const CHARS_PER_TOKEN = 4
    const totalChars = sessionStore.turns.reduce((sum, t) => sum + (t.content?.length || 0), 0)
    contextUsed.value = Math.round(totalChars / CHARS_PER_TOKEN)
    contextMax.value = 128000
  }
}

async function fetchSbertHarmony() {
  if (!sbertMeterEnabled.value) return
  try {
    const r = await api.get(`/api/sessions/${sessionId.value}/sbert-harmony`)
    harmonyScore.value = r.data.harmony_score
  } catch (err) {
    console.warn('S-BERT harmony fetch failed:', err.message)
    harmonyScore.value = null
  }
}

async function handleCompact() {
  compactLoading.value = true
  try {
    await api.post(`/api/sessions/${sessionId.value}/compact`, { rounds_to_keep: 2 })
    await fetchContextUsage()
  } catch (err) {
    error.value = t('sessionLive.compactionFailed') + (err.response?.data?.detail || err.message)
  }
  compactLoading.value = false
}

// Attach view-level SSE event listeners to a given EventSource.
// Note: The store's connectToStream() also registers listeners on the same EventSource
// for data-persistence concerns (turns, observerData, etc.). These view-level listeners
// handle UI-only concerns (thinkingSpeaker indicator, agenda display, context fetch).
// The store's 'ping' handler is sufficient — no redundant handler added here.
function attachSseListeners(es) {
  es.addEventListener('turn_start', (e) => {
    if (thinkingIndicatorEnabled.value) {
      const data = JSON.parse(e.data)
      thinkingSpeaker.value = { speaker: data.speaker, speaker_name: data.speaker_name }
    }
  })
  // turn_end: clear thinking indicator, refresh S-BERT harmony and context usage.
  // Context fetch is on turn_end (primary streaming event) AND turn (legacy fallback).
  es.addEventListener('turn_end', () => {
    thinkingSpeaker.value = null
    fetchSbertHarmony()
    fetchContextUsage()
  })
  es.addEventListener('turn', () => {
    thinkingSpeaker.value = null
    fetchContextUsage()
  })
  es.addEventListener('agenda_init', (e) => {
    const data = JSON.parse(e.data)
    agenda.value = { items: (data.items || []).map(item => ({ ...item, votes: {}, tally: emptyTally() })) }
  })
  es.addEventListener('observer', (e) => {
    const eventData = JSON.parse(e.data)
    if (eventData.agenda_votes && agenda.value.items && agenda.value.items.length) {
      agenda.value.items = agenda.value.items.map(item => {
        const vote = eventData.agenda_votes[item.key]
        if (!vote) return item
        const votes = { ...(item.votes || {}), [eventData.speaker]: { stance: vote.stance, confidence: vote.confidence, turn: eventData.turn } }
        const tally = emptyTally()
        Object.values(votes).forEach(v => { tally[v.stance] = (tally[v.stance] || 0) + 1 })
        return { ...item, votes, tally }
      })
    }
  })
}

async function handleStart() {
  try {
    await sessionStore.startSession(sessionId.value, {
      num_rounds: config.value.num_rounds,
      moderator_style: config.value.moderator_style,
      moderator_name: config.value.moderator_name,
      moderator_title: config.value.moderator_title,
      moderator_mandate: config.value.moderator_mandate,
      moderator_persona_prompt: config.value.moderator_persona_prompt,
      agents_per_turn: config.value.agents_per_turn,
      anti_groupthink: config.value.anti_groupthink,
      devil_advocate_round: config.value.devil_advocate_round,
      temperature_override: config.value.temperature_override,
      private_thread_limit: config.value.private_thread_limit,
      private_thread_depth: config.value.private_thread_depth,
      private_thread_quota_mode: config.value.private_thread_quota_mode,
      context_window_strategy: config.value.context_window_strategy,  // #200: forward strategy to backend
    })

    // Attach SSE listeners to the new EventSource
    const es = sessionStore.eventSource
    if (es) attachSseListeners(es)
  } catch (err) {
    error.value = err.response?.data?.detail || t('sessionLive.failedToStart')
  }
}

async function handleStop() {
  await sessionStore.stopCurrentSession(sessionId.value)
}

// Pause / Resume / Recover

const canRecover = computed(() => {
  const s = sessionStore.status
  const hasEngine = !!sessionStore.eventSource
  return (s === 'paused' || s === 'running' || s === 'failed' || s === 'stopped') && !hasEngine
})

async function handlePause() {
  try {
    await sessionStore.pauseCurrentSession(sessionId.value)
  } catch (err) {
    error.value = err.response?.data?.detail || t('sessionLive.failedToPause')
  }
}

async function handleResume() {
  try {
    await sessionStore.resumeCurrentSession(sessionId.value)
  } catch (err) {
    if (err.response?.status === 404) {
      await handleRecover()
    } else {
      error.value = err.response?.data?.detail || t('sessionLive.failedToResume')
    }
  }
}

async function handleRecover() {
  try {
    // Load existing messages first (recover starts from the last known state)
    const r = await api.get(`/api/sessions/${sessionId.value}/messages`)
    const msgs = r.data ?? []
    sessionStore.turns = msgs.map(msg => ({ ...msg, thinking: '' }))

    await sessionStore.recoverCurrentSession(sessionId.value)

    // Attach SSE listeners to the new EventSource opened by recoverCurrentSession
    const es = sessionStore.eventSource
    if (es) attachSseListeners(es)
  } catch (err) {
    error.value = err.response?.data?.detail || t('sessionLive.failedToRecover')
  }
}

// #203: Continue a stopped/complete session with additional rounds
async function handleContinue() {
  try {
    await sessionStore.continueCurrentSession(sessionId.value, config.value.num_rounds || 5)
    const es = sessionStore.eventSource
    if (es) attachSseListeners(es)
  } catch (err) {
    error.value = err.response?.data?.detail || t('sessionLive.failedToStart')
  }
}

async function handleInject(content, asModerator) {
  try {
    await sessionStore.sendInjectMessage(sessionId.value, content, asModerator)
  } catch {
    error.value = t('sessionLive.failedToInject')
  }
}

function handleMute(slug) {
  sessionStore.muteAgent(slug)
  if (sessionStore.agentOverrides[slug]?.is_silenced) {
    handleInject(`[SYSTEM: Agent ${slug} has been silenced by the consultant]`, true)
  }
}

function handleOverride(slug, overrides) {
  sessionStore.updateAgentOverride(slug, overrides)
}

const agentSentiments = computed(() =>
  Object.entries(sessionStore.observerData).map(([slug, obs]) => ({
    slug,
    name: obs.speaker_name,
    overall: obs.sentiment?.overall ?? 0,
  }))
)

const riskAgents = computed(() =>
  Object.values(sessionStore.observerData)
    .filter(o => (o.sentiment?.overall ?? 0) < 0)
    .map(o => ({
      name: o.speaker_name,
      score: Math.abs(o.sentiment?.overall ?? 0) * 10,
      level: Math.abs(o.sentiment?.overall ?? 0) > 0.5 ? 'HIGH'
           : Math.abs(o.sentiment?.overall ?? 0) > 0.2 ? 'MEDIUM' : 'LOW',
    }))
    .sort((a, b) => b.score - a.score)
)

const consensusScore = computed(() => {
  const rounds = sessionStore.analyticsRounds
  if (!rounds.length) return 0
  return rounds[rounds.length - 1]?.consensus_score ?? 0
})

const timelineRounds = computed(() =>
  sessionStore.analyticsRounds.map(r => ({ consensus_score: r.consensus_score ?? 0 }))
)

// Context meter computed
const contextPercent = computed(() => {
  if (!contextMax.value) return 0
  return Math.round((contextUsed.value / contextMax.value) * 100)
})

const contextBarColor = computed(() => {
  if (contextPercent.value > 80) return 'var(--danger)'
  if (contextPercent.value > 50) return 'var(--warn)'
  return 'var(--success)'
})

function formatTokens(n) {
  if (n >= 1000) return Math.round(n / 1000) + 'k'
  return String(n)
}

const moderatorDisplayName = computed(() => config.value.moderator_name || 'Moderator')

// Agents list for DAG visualization (agreement/disagreement graph)
const graphAgents = computed(() =>
  participants.value.map(p => ({ slug: p.slug, name: p.name, color: p.color }))
)

const sbertColor = computed(() => {
  if (harmonyScore.value === null) return 'var(--text-muted)'
  if (harmonyScore.value >= 0.7) return 'var(--success, #10b981)'
  if (harmonyScore.value >= 0.4) return 'var(--warn, #f59e0b)'
  return 'var(--danger, #ef4444)'
})
</script>

<template>
  <div v-if="error" style="padding: 32px;">
    <div class="page-header">
      <div>
        <h1 class="page-title">{{ t('sessionLive.sessionError') }}</h1>
        <p class="page-subtitle">{{ error }}</p>
      </div>
      <button class="btn btn-ghost" @click="router.push('/sessions')">{{ t('sessionLive.back') }}</button>
    </div>
  </div>

  <div v-else-if="!sessionStore.currentSession" class="session-loading-state">
    <Spinner variant="ring" size="44px" color="var(--accent)" />
    <p class="session-loading-text">{{ t('sessionLive.loadingSession') }}</p>
  </div>

  <div v-else class="session-layout">
    <!-- Slim toolbar: title + status + config + analytics + back -->
    <div class="page-header session-toolbar">
      <div class="toolbar-left">
        <h1 class="page-title session-title">
          {{ sessionStore.currentSession.title }}
        </h1>
        <StatusBadge :status="sessionStore.status" />
      </div>
      <div class="toolbar-right">
        <button class="btn btn-ghost btn-sm" @click="configOpen = true">{{ t('sessionLive.config') }}</button>
        <button v-if="sessionStore.status === 'complete' || sessionStore.status === 'stopped'"
          class="btn btn-ghost btn-sm"
          @click="$router.push(`/sessions/${sessionId}/analytics`)">
          {{ t('sessionLive.analytics') }}
        </button>
        <button class="btn btn-ghost" @click="router.push('/sessions')">{{ t('sessionLive.backArrow') }}</button>
      </div>
    </div>

    <div class="session-panels">
      <!-- Left: Agent panel -->
      <div :class="['session-left-panel', { collapsed: !leftPanelOpen }]">
        <AgentPanel
          :participants="participants"
          :observer-data="sessionStore.observerData"
          :agent-overrides="sessionStore.agentOverrides"
          :analytics-rounds="sessionStore.analyticsRounds"
          :thinking-speaker="thinkingSpeaker"
          @mute="handleMute"
          @update-override="handleOverride"
        />
      </div>

      <!-- Left panel toggle -->
      <button
        class="panel-toggle panel-toggle-left"
        :aria-label="leftPanelOpen ? t('sessionLive.collapseAgentPanel') : t('sessionLive.expandAgentPanel')"
        @click="leftPanelOpen = !leftPanelOpen"
      >
        {{ leftPanelOpen ? '‹' : '›' }}
      </button>

      <!-- Center: Transcript -->
      <div class="session-center">
        <DebateTranscript
          :turns="sessionStore.turns"
          :observer-data="sessionStore.observerData"
          :agent-overrides="sessionStore.agentOverrides"
          :status="sessionStore.status"
          :stakeholders="stakeholderMap"
          :thinking-speaker="thinkingSpeaker"
          :moderator-name="moderatorDisplayName"
          :streaming-messages="sessionStore.streamingMessages"
          :status-message="sessionStore.statusMessage"
          style="flex: 1; min-height: 0;"
        />
        <!-- CR-011: Whisper Channels panel (overseer view) -->
        <WhisperPanel
          v-if="featureFlags.private_threads"
          :session-id="sessionId"
        />
      </div>

      <!-- Right panel toggle -->
      <button
        class="panel-toggle panel-toggle-right"
        :aria-label="rightPanelOpen ? t('sessionLive.collapseMetricsPanel') : t('sessionLive.expandMetricsPanel')"
        @click="rightPanelOpen = !rightPanelOpen"
      >
        {{ rightPanelOpen ? '›' : '‹' }}
      </button>

      <!-- Right: Metrics panel -->
      <div :class="['session-right-panel', { collapsed: !rightPanelOpen }]">
        <!-- S-BERT Harmony Meter (BUG-006) -->
        <div v-if="sbertMeterEnabled && harmonyScore !== null" class="sbert-meter">
          <div class="sbert-label">{{ t('sessionLive.sbertHarmony') }}</div>
          <div class="sbert-bar">
            <div class="sbert-fill" :style="{ width: (harmonyScore * 100) + '%', background: sbertColor }"></div>
          </div>
          <span class="sbert-value">{{ (harmonyScore * 100).toFixed(0) }}%</span>
        </div>

        <AgendaPanel :agenda="agenda" />
        <ConsensusGauge :value="consensusScore" />
        <SentimentPanel :agents="agentSentiments" />
        <RiskTable :agents="riskAgents" />
        <ConsensusTimeline :rounds="timelineRounds" />
        <SynthesesPanel :syntheses="sessionStore.syntheses" />

        <div class="simulation-disclaimer">
          ⚠️ {{ t('sessionLive.simulationDisclaimer') }}
        </div>
      </div>
    </div>

    <!-- Bottom bar: inject, controls, context meter -->
    <SessionBottomBar
      :status="sessionStore.status"
      :has-event-source="!!sessionStore.eventSource"
      :can-recover="canRecover"
      :context-meter-enabled="contextMeterEnabled"
      :context-percent="contextPercent"
      :context-bar-color="contextBarColor"
      :context-used-formatted="formatTokens(contextUsed)"
      :context-max-formatted="formatTokens(contextMax)"
      :thinking-speaker="thinkingSpeaker"
      :thinking-indicator-enabled="thinkingIndicatorEnabled"
      :compact-conversation-enabled="compactConversationEnabled"
      :compact-loading="compactLoading"
      @start="handleStart"
      @stop="handleStop"
      @pause="handlePause"
      @resume="handleResume"
      @recover="handleRecover"
      @continue="handleContinue"
      @inject="handleInject"
      @compact="handleCompact"
    />

    <!-- Bottom analytics bar: DAG visualization -->
    <BottomAnalyticsBar
      v-if="dagVisualizationEnabled"
      :agents="graphAgents"
      :observer-data="sessionStore.observerData"
    />

    <ScaleTransition>
      <ConfigDrawer v-if="configOpen" v-model="config" :feature-flags="featureFlags" @close="configOpen = false" />
    </ScaleTransition>
  </div>
</template>

<style scoped>
.session-layout {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 0;
  overflow: hidden;
}

/* Toolbar */
.session-toolbar {
  padding: var(--space-4) var(--space-6);
  margin-bottom: 0;
  flex-shrink: 0;
  border-bottom: 1px solid var(--border);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
}
.toolbar-left {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-width: 0;
}
.toolbar-right {
  display: flex;
  gap: var(--space-2);
  flex-shrink: 0;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.session-title {
  font-family: var(--font-display);
  font-size: 16px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.session-panels {
  display: flex;
  flex: 1;
  min-height: 0;
  gap: 0;
}

/* Left panel */
.session-left-panel {
  width: 200px;
  flex-shrink: 0;
  border-right: 1px solid var(--border);
  padding: var(--space-4);
  overflow-y: auto;
  transition: width var(--transition-base), padding var(--transition-base), opacity var(--transition-base), border-radius var(--transition-base);
}
.session-left-panel.collapsed {
  width: 0;
  padding: 0;
  overflow: hidden;
  opacity: 0;
  border-radius: 0;
}

/* Center */
.session-center {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding: var(--space-4);
  border-right: 1px solid var(--border);
}

/* Right panel */
.session-right-panel {
  width: 280px;
  flex-shrink: 0;
  overflow-y: auto;
  padding: var(--space-4);
  transition: width var(--transition-base), padding var(--transition-base), opacity var(--transition-base), border-radius var(--transition-base);
}
.session-right-panel.collapsed {
  width: 0;
  padding: 0;
  overflow: hidden;
  opacity: 0;
  border-radius: 0;
}

/* Toggle buttons */
.panel-toggle {
  flex-shrink: 0;
  align-self: center;
  z-index: 10;
  width: 24px;
  height: 40px;
  background: var(--surface);
  border: 1px solid var(--border);
  color: var(--text-muted);
  cursor: pointer;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  line-height: 1;
  box-shadow: var(--shadow-xs);
  transition: transform var(--transition-fast), color var(--transition-fast), background var(--transition-fast);
}
.panel-toggle:hover {
  color: var(--text);
  background: var(--surface-hover);
  transform: scaleY(1.1);
}
.panel-toggle-left {
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
}
.panel-toggle-right {
  border-radius: var(--radius-sm) 0 0 var(--radius-sm);
}

/* Context meter */
.context-meter {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: 11px;
  color: var(--text-muted);
}
.context-meter-bar {
  width: 80px;
  height: 10px;
  background: var(--border);
  border-radius: var(--radius-full);
  overflow: hidden;
  box-shadow: var(--shadow-xs);
}
.context-meter-fill {
  height: 100%;
  border-radius: var(--radius-full);
  transition: width var(--transition-slow), background var(--transition-slow);
  box-shadow: 0 0 6px currentColor;
}
.context-meter-label {
  white-space: nowrap;
}

/* S-BERT Harmony Meter */
.sbert-meter {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) 0;
  margin-bottom: var(--space-2);
  border-bottom: 1px solid var(--border);
}
.sbert-label {
  font-size: 11px;
  color: var(--text-muted);
  white-space: nowrap;
}
.sbert-bar {
  flex: 1;
  height: 10px;
  background: var(--border);
  border-radius: var(--radius-full);
  overflow: hidden;
  box-shadow: var(--shadow-xs);
}
.sbert-fill {
  height: 100%;
  border-radius: var(--radius-full);
  transition: width var(--transition-slow), background var(--transition-slow);
  box-shadow: 0 0 6px currentColor;
}
.sbert-value {
  font-size: 11px;
  color: var(--text-muted);
  min-width: 32px;
  text-align: right;
}

/* Session loading state — centered ring spinner */
.session-loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100vh;
  gap: var(--space-4);
}
.session-loading-text {
  color: var(--text-muted);
  font-size: 14px;
  margin: 0;
}

/* Inline compact spinner */
.compact-spinner {
  margin-right: 4px;
  vertical-align: middle;
}

/* Compact Conversation bar */
.compact-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  margin-bottom: var(--space-2);
  border-bottom: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-alt);
  font-size: 11px;
  color: var(--text-muted);
}
.compact-btn {
  font-size: 11px;
  padding: var(--space-1) var(--space-2);
}

/* Simulation disclaimer */
.simulation-disclaimer {
  margin-top: var(--space-4);
  padding: var(--space-2) var(--space-3);
  background: rgba(210, 153, 34, 0.1);
  border-radius: var(--radius-sm);
  font-size: 11px;
  color: var(--warn);
  box-shadow: var(--shadow-xs);
}

@media (max-width: 768px) {
  .session-left-panel {
    width: 0;
    padding: 0;
    overflow: hidden;
    opacity: 0;
  }
  .session-right-panel {
    width: 0;
    padding: 0;
    overflow: hidden;
    opacity: 0;
  }
}
</style>
