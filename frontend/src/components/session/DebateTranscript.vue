<script setup>
import { ref, watch, nextTick, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import TurnCard from './TurnCard.vue'
import EmptyState from '../common/EmptyState.vue'
import Spinner from '../common/Spinner.vue'

const { t } = useI18n()

const props = defineProps({
  turns: { type: Array, default: () => [] },
  observerData: { type: Object, default: () => ({}) },
  agentOverrides: { type: Object, default: () => ({}) },
  status: String,
  stakeholders: { type: Object, default: () => ({}) },
  thinkingSpeaker: { type: Object, default: null },
  moderatorName: { type: String, default: 'Moderator' },
  streamingMessages: { type: Object, default: () => ({}) },
  statusMessage: { type: Object, default: null },
})

const container = ref(null)
const autoScroll = ref(true)

function onScroll() {
  const el = container.value
  if (!el) return
  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 50
  autoScroll.value = atBottom
}

watch(() => props.turns, () => {
  if (autoScroll.value) {
    nextTick(() => container.value?.scrollTo({ top: container.value.scrollHeight, behavior: 'smooth' }))
  }
}, { deep: true })

watch(() => props.thinkingSpeaker, () => {
  if (autoScroll.value) {
    nextTick(() => container.value?.scrollTo({ top: container.value.scrollHeight, behavior: 'smooth' }))
  }
})

const groupedTurns = computed(() => {
  const groups = []
  let currentRound = null
  let prevSpeaker = null
  for (const turn of props.turns) {
    if (turn.round !== currentRound) {
      currentRound = turn.round
      prevSpeaker = null
      groups.push({ type: 'separator', round: turn.round })
    }
    const isMod = (turn.speaker === 'moderator' || turn.stage === 'synthesis')
    const isSameSpeaker = (turn.speaker === prevSpeaker) && !isMod
    groups.push({ type: 'turn', turn, showHeader: !isSameSpeaker })
    prevSpeaker = turn.speaker
  }
  return groups
})

const thinkingAvatarUrl = computed(() => {
  if (!props.thinkingSpeaker) return null
  const stk = props.stakeholders[props.thinkingSpeaker.speaker]
  return stk?.avatar_url || null
})

const thinkingColor = computed(() => {
  if (!props.thinkingSpeaker) return '#888'
  const stk = props.stakeholders[props.thinkingSpeaker.speaker]
  return stk?.color || '#888'
})

const thinkingInitial = computed(() => {
  if (!props.thinkingSpeaker) return '?'
  return (props.thinkingSpeaker.speaker_name || props.thinkingSpeaker.speaker || '?').charAt(0).toUpperCase()
})

// Streaming bubble: build a list of in-progress turns from streamingMessages
const activeStreamingTurns = computed(() => {
  const entries = []
  for (const [speaker, msg] of Object.entries(props.streamingMessages)) {
    if (!msg.content && !msg.thinking) continue
    const stk = props.stakeholders[speaker]
    entries.push({
      speaker,
      speaker_name: stk?.name || speaker,
      content: msg.content || '',
      thinking: msg.thinking || '',
      color: stk?.color || '#888',
      avatar_url: stk?.avatar_url || null,
      stage: 'response',
      round: 0,
      _streaming: true,
    })
  }
  return entries
})

// Auto-scroll when streaming content updates
watch(() => props.streamingMessages, () => {
  if (autoScroll.value) {
    nextTick(() => container.value?.scrollTo({ top: container.value.scrollHeight, behavior: 'smooth' }))
  }
}, { deep: true })

const emptyTitle = computed(() =>
  props.status === 'pending' ? t('transcript.startWargame') : t('transcript.waitingForTurn')
)

const statusPhaseLabel = computed(() => {
  if (!props.statusMessage) return ''
  const phase = props.statusMessage.phase
  const phaseMap = {
    extracting_agenda: t('transcript.statusExtracting', 'Extracting agenda...'),
    moderator_preparing: t('transcript.statusModeratorPreparing', 'Moderator is preparing...'),
    preparing_round: t('transcript.statusPreparingRound', { round: props.statusMessage.round || 1 }, `Preparing Round ${props.statusMessage.round || 1}...`),
    agent_thinking: t('transcript.statusAgentThinking', { name: props.statusMessage.speaker_name || '' }, `${props.statusMessage.speaker_name || 'Agent'} is thinking...`),
    observer_analyzing: t('transcript.statusObserverAnalyzing', 'Analyzing sentiment...'),
    synthesizing: t('transcript.statusSynthesizing', 'Synthesizing insights...'),
    computing_analytics: t('transcript.statusComputingAnalytics', 'Computing analytics...'),
  }
  return phaseMap[phase] || ''
})

// Show the latest portion of the thinking text for the streaming preview.
// Keeps the last THINKING_PREVIEW_LINES lines so the box stays at a fixed height
// while new thinking tokens arrive. Adjust THINKING_PREVIEW_LINES to change height.
const THINKING_PREVIEW_LINES = 6

function truncateThinking(text) {
  if (!text) return ''
  const lines = text.split('\n')
  if (lines.length > THINKING_PREVIEW_LINES) {
    return lines.slice(-THINKING_PREVIEW_LINES).join('\n')
  }
  return text
}
</script>

<template>
  <div class="transcript-wrapper">
    <div class="section-title" style="margin-top: 0; flex-shrink: 0;">{{ t('transcript.debateTranscript') }}</div>
    <div
      ref="container"
      class="transcript-scroll"
      @scroll="onScroll"
    >
      <!-- Empty state: static when pending, animated spinner when running -->
      <div v-if="turns.length === 0 && status === 'running'" class="waiting-state">
        <div class="waiting-spinner-wrap">
          <Spinner variant="ring" size="48px" color="var(--accent)" />
        </div>
        <div class="waiting-title">{{ statusMessage?.message || t('transcript.waitingForTurn') }}</div>
        <div class="waiting-subtitle">{{ statusMessage ? statusPhaseLabel : t('transcript.preparingAgents') }}</div>
        <div class="waiting-dots-row">
          <span class="waiting-dot" style="animation-delay: 0s;"></span>
          <span class="waiting-dot" style="animation-delay: 0.2s;"></span>
          <span class="waiting-dot" style="animation-delay: 0.4s;"></span>
        </div>
      </div>
      <EmptyState
        v-else-if="turns.length === 0"
        icon="&#128172;"
        :title="emptyTitle"
      />

      <template v-for="(item, i) in groupedTurns" :key="i">
        <!-- Round separator -->
        <div v-if="item.type === 'separator'" class="round-separator">
          <div class="round-separator-line"></div>
          <span class="round-separator-badge">{{ t('transcript.round', { round: item.round }) }}</span>
          <div class="round-separator-line"></div>
        </div>
        <TurnCard
          v-else
          :turn="item.turn"
          :observer="observerData[item.turn.speaker]"
          :is-muted="agentOverrides[item.turn.speaker]?.is_silenced"
          :stakeholders="stakeholders"
          :show-header="item.showHeader"
          :moderator-name="moderatorName"
        />
      </template>

      <!-- Streaming in-progress bubbles -->
      <template v-for="st in activeStreamingTurns" :key="'stream-' + st.speaker">
        <div class="stream-bubble" :style="{ '--agent-color': st.color }">
          <div class="stream-bubble-row">
            <!-- Avatar -->
            <div class="stream-avatar-col">
              <div class="stream-avatar-ring" :style="{ '--agent-color': st.color }">
                <img
                  v-if="st.avatar_url"
                  :src="st.avatar_url"
                  class="stream-avatar"
                  :alt="st.speaker_name"
                />
                <div v-else class="stream-avatar-fallback" :style="{ background: st.color }">
                  {{ (st.speaker_name || st.speaker || '?').charAt(0).toUpperCase() }}
                </div>
              </div>
            </div>

            <!-- Card -->
            <div class="stream-card">
              <div class="stream-card-accent" :style="{ background: st.color }"></div>
              <div class="stream-card-body">
                <div class="stream-card-header">
                  <strong class="stream-speaker" :style="{ color: st.color }">{{ st.speaker_name }}</strong>
                  <span class="stream-badge">
                    <span class="stream-dot-live"></span>
                    {{ t('transcript.streaming') }}
                  </span>
                </div>

                <!-- Thinking preview -->
                <div v-if="st.thinking" class="stream-thinking-preview">
                  <span class="stream-thinking-icon">&#128173;</span>
                  <span class="stream-thinking-text">{{ truncateThinking(st.thinking) }}</span>
                </div>

                <!-- Content with cursor -->
                <div class="stream-content">{{ st.content }}<span class="stream-cursor"></span></div>
              </div>
            </div>
          </div>
        </div>
      </template>

      <!-- Thinking indicator (when no streaming bubble yet) -->
      <div v-if="thinkingSpeaker && activeStreamingTurns.length === 0" class="thinking-indicator">
        <div class="thinking-row">
          <div class="thinking-avatar-col">
            <div class="thinking-avatar-glow" :style="{ '--glow-color': thinkingColor }">
              <img v-if="thinkingAvatarUrl" :src="thinkingAvatarUrl" class="thinking-avatar" />
              <div v-else class="thinking-avatar-fallback" :style="{ background: thinkingColor }">
                {{ thinkingInitial }}
              </div>
            </div>
          </div>
          <div class="thinking-body">
            <Spinner size="14px" color="var(--accent)" class="thinking-spinner" />
            <strong class="thinking-name">{{ thinkingSpeaker.speaker_name }}</strong>
            <span class="thinking-label"> {{ t('transcript.isThinking') }}</span>
            <span class="thinking-dots">
              <span class="dot"></span><span class="dot"></span><span class="dot"></span>
            </span>
          </div>
        </div>
      </div>

      <!-- Inline status notification -->
      <div v-if="statusMessage && turns.length > 0" class="inline-status">
        <Spinner size="12px" color="var(--accent)" />
        <span class="inline-status-text">{{ statusMessage.message }}</span>
      </div>
    </div>

    <Transition name="jump-up">
      <div v-if="!autoScroll" class="jump-to-latest">
        <button class="btn btn-ghost jump-btn"
          @click="() => { autoScroll = true; container?.scrollTo({ top: container.scrollHeight, behavior: 'smooth' }) }">
          {{ t('transcript.jumpToLatest') }}
        </button>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.transcript-wrapper {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.transcript-scroll {
  flex: 1;
  overflow-y: auto;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px 14px;
  box-shadow: var(--shadow-sm);
}

/* ================================================================
   WAITING STATE
   ================================================================ */
.waiting-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-12) var(--space-6);
  text-align: center;
  animation: fade-in 400ms ease;
}
.waiting-spinner-wrap {
  margin-bottom: var(--space-5);
  animation: waiting-breathe 2.5s infinite ease-in-out;
}
@keyframes waiting-breathe {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.08); opacity: 0.85; }
}
.waiting-title {
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: var(--space-1);
}
.waiting-subtitle {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: var(--space-4);
}
.waiting-dots-row {
  display: flex;
  gap: 6px;
}
.waiting-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--accent);
  animation: waiting-dot-bounce 1.4s infinite ease-in-out;
}
@keyframes waiting-dot-bounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.3; }
  40% { transform: scale(1.2); opacity: 1; }
}

/* ================================================================
   ROUND SEPARATOR — pill badge between gradient lines
   ================================================================ */
.round-separator {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 20px 0 12px;
  padding: 0 4px;
}
.round-separator-line {
  flex: 1;
  height: 1px;
  background: linear-gradient(
    to right,
    transparent,
    var(--border) 20%,
    var(--border) 80%,
    transparent
  );
}
.round-separator-badge {
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 1.2px;
  white-space: nowrap;
  text-transform: uppercase;
  flex-shrink: 0;
  background: var(--surface-alt);
  border: 1px solid var(--border);
  padding: 3px 12px;
  border-radius: var(--radius-full);
}

/* ================================================================
   STREAMING BUBBLE — mirrors TurnCard but with live indicator
   ================================================================ */
.stream-bubble {
  margin-top: 14px;
  animation: msg-in 300ms ease;
}
.stream-bubble-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

/* Avatar */
.stream-avatar-col {
  flex-shrink: 0;
  width: 44px;
  padding-top: 2px;
}
.stream-avatar-ring {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  padding: 2px;
  background: linear-gradient(135deg, var(--agent-color), color-mix(in srgb, var(--agent-color) 50%, transparent));
  box-shadow: 0 2px 8px color-mix(in srgb, var(--agent-color) 30%, transparent);
  animation: ring-pulse 2s infinite ease-in-out;
}
@keyframes ring-pulse {
  0%, 100% { box-shadow: 0 2px 8px color-mix(in srgb, var(--agent-color) 30%, transparent); }
  50% { box-shadow: 0 2px 14px color-mix(in srgb, var(--agent-color) 50%, transparent); }
}
.stream-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  object-fit: cover;
  display: block;
  border: 2px solid var(--surface);
}
.stream-avatar-fallback {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 16px;
  color: #fff;
  border: 2px solid var(--surface);
}

/* Card */
.stream-card {
  flex: 1;
  min-width: 0;
  display: flex;
  background: color-mix(in srgb, var(--agent-color) 6%, var(--surface));
  border: 1px solid color-mix(in srgb, var(--agent-color) 20%, var(--border));
  border-radius: 4px var(--radius) var(--radius) var(--radius);
  box-shadow: var(--shadow-xs);
  overflow: hidden;
  animation: stream-border-glow 2s infinite ease-in-out;
}
@keyframes stream-border-glow {
  0%, 100% { border-color: color-mix(in srgb, var(--agent-color) 20%, var(--border)); }
  50% { border-color: color-mix(in srgb, var(--agent-color) 40%, var(--border)); }
}
.stream-card-accent {
  width: 4px;
  flex-shrink: 0;
  animation: accent-shimmer 1.5s infinite ease-in-out;
}
@keyframes accent-shimmer {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
.stream-card-body {
  flex: 1;
  min-width: 0;
  padding: 10px 14px;
}
.stream-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.stream-speaker {
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.2px;
}
.stream-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 10px;
  color: var(--accent);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.stream-dot-live {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
  animation: live-pulse 1s infinite;
}
@keyframes live-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.4; transform: scale(0.7); }
}

/* Thinking preview — live scrollable box during streaming */
.stream-thinking-preview {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 6px 8px;
  margin-bottom: 6px;
  background: var(--accent-glow);
  border-left: 2px solid var(--accent);
  border-radius: 0 var(--radius-xs, 4px) var(--radius-xs, 4px) 0;
  font-size: 11px;
  line-height: 1.5;
  color: var(--text-muted);
  /* Allow ~6 lines of thinking text to show before scrolling */
  max-height: calc(6 * 1.5 * 11px + 12px); /* 6 lines × line-height × font-size + padding */
  overflow-y: auto;
  overflow-x: hidden;
}
.stream-thinking-icon {
  flex-shrink: 0;
  font-size: 12px;
  padding-top: 1px;
}
.stream-thinking-text {
  font-style: italic;
  white-space: pre-wrap;
  word-wrap: break-word;
  overflow-wrap: break-word;
  min-width: 0;
  flex: 1;
}

/* Content with cursor */
.stream-content {
  white-space: pre-wrap;
  line-height: 1.6;
  font-size: 13.5px;
  color: var(--text);
}
.stream-cursor {
  display: inline-block;
  width: 2px;
  height: 1em;
  background: var(--accent);
  margin-left: 1px;
  vertical-align: text-bottom;
  animation: cursor-blink 0.8s infinite;
}
@keyframes cursor-blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

/* ================================================================
   THINKING INDICATOR
   ================================================================ */
.thinking-indicator {
  margin-top: 14px;
  padding: 8px 0;
}
.thinking-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.thinking-avatar-col { flex-shrink: 0; width: 44px; }

.thinking-avatar-glow {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  animation: thinking-glow-pulse 1.8s infinite ease-in-out;
}
@keyframes thinking-glow-pulse {
  0%, 100% { box-shadow: 0 0 0 0 transparent; }
  50%       { box-shadow: 0 0 12px 5px var(--glow-color, rgba(233,69,96,0.35)); }
}

.thinking-avatar {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  object-fit: cover;
  display: block;
}
.thinking-avatar-fallback {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 16px;
  color: #fff;
}
.thinking-body {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 13px;
  color: var(--text-muted);
  background: var(--surface);
  border: 1px solid var(--border);
  padding: 8px 14px;
  border-radius: var(--radius-full);
}
.thinking-spinner { margin-right: 4px; flex-shrink: 0; }
.thinking-name { color: var(--text); }
.thinking-label { font-style: italic; }
.thinking-dots {
  display: inline-flex;
  gap: 3px;
  margin-left: 6px;
}
.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-muted);
  animation: dot-pulse 1.4s infinite ease-in-out;
}
.dot:nth-child(2) { animation-delay: 0.2s; }
.dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes dot-pulse {
  0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
  40% { opacity: 1; transform: scale(1); }
}

/* ================================================================
   INLINE STATUS NOTIFICATION
   ================================================================ */
.inline-status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  margin-top: 10px;
  font-size: 11px;
  color: var(--text-muted);
  background: var(--surface);
  border-radius: var(--radius-full);
  border: 1px solid var(--border);
  animation: fade-in 200ms ease;
}
.inline-status-text {
  font-style: italic;
}

/* ================================================================
   JUMP TO LATEST
   ================================================================ */
.jump-to-latest {
  text-align: center;
  padding: 4px;
}
.jump-btn {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: var(--radius-sm);
}
.jump-up-enter-active {
  animation: slide-up 200ms ease;
}
.jump-up-leave-active {
  animation: slide-up 150ms ease reverse;
}
@keyframes slide-up {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}
@keyframes msg-in {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}
@keyframes fade-in {
  from { opacity: 0; }
  to   { opacity: 1; }
}
</style>
