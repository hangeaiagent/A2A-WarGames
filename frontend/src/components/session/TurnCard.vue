<script setup>
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTTS } from '../../composables/useTTS'
import CollapseTransition from '../transitions/CollapseTransition.vue'

const { t } = useI18n()

const props = defineProps({
  turn: Object,
  observer: Object,
  thinking: { type: String, default: '' },
  isMuted: Boolean,
  stakeholders: { type: Object, default: () => ({}) },
  showHeader: { type: Boolean, default: true },
  moderatorName: { type: String, default: 'Moderator' },
})

// Collapsible thinking bubble state — collapsed by default
const thinkingExpanded = ref(false)

// Resolved thinking text: prefer prop, fall back to turn.thinking
const thinkingText = computed(() => props.thinking || props.turn?.thinking || '')

const isMod = computed(() => props.turn.speaker === 'moderator' || props.turn.stage === 'synthesis')

const isFallbackMessage = computed(() => {
  const c = (props.turn.content || '').toLowerCase()
  return c.includes('temporarily unavailable') || c.includes('chose to remain silent')
})

const stakeholder = computed(() => props.stakeholders[props.turn.speaker] || null)

const avatarUrl = computed(() => stakeholder.value?.avatar_url || null)

const speakerColor = computed(() => stakeholder.value?.color || '#888')

const initials = computed(() => {
  const name = props.turn.speaker_name || props.turn.speaker || ''
  return name.charAt(0).toUpperCase()
})

const displayName = computed(() => {
  if (isMod.value) return props.moderatorName
  return props.turn.speaker_name
})

const timestamp = computed(() => {
  if (!props.turn.created_at) return ''
  try {
    const d = new Date(props.turn.created_at)
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch {
    return ''
  }
})

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

function renderContent(text) {
  if (!text) return ''
  return escapeHtml(text).replace(/@(\w+)/g, '<span class="mention">@$1</span>')
}

const sentimentClass = computed(() => {
  const val = props.observer?.sentiment?.overall ?? 0
  if (val > 0.1) return 'sentiment-positive'
  if (val < -0.1) return 'sentiment-negative'
  return 'sentiment-neutral'
})

const { speak, stop, isPlaying, isEnabled: ttsEnabled } = useTTS()
</script>

<template>
  <!-- Moderator message: distinct card with centered accent -->
  <div v-if="isMod" :class="['turn-mod', { 'turn-muted': isMuted }]">
    <div class="turn-mod-card">
      <div class="turn-mod-accent"></div>
      <div class="turn-mod-inner">
        <div class="turn-mod-icon-wrap">
          <span class="turn-mod-icon">&#9878;&#65039;</span>
        </div>
        <div class="turn-mod-body">
          <div v-if="showHeader" class="turn-mod-header">
            <strong class="turn-mod-name">{{ displayName }}</strong>
            <span v-if="timestamp" class="turn-timestamp">{{ timestamp }}</span>
          </div>
          <div class="turn-mod-content" v-html="renderContent(turn.content)"></div>
        </div>
      </div>
    </div>
  </div>

  <!-- Normal speaker message: modern chat bubble with colored accent -->
  <div v-else :class="['turn-bubble', { 'turn-muted': isMuted, 'turn-continuation': !showHeader }]">
    <div class="turn-bubble-row">
      <!-- Avatar column -->
      <div class="turn-avatar-col">
        <template v-if="showHeader">
          <div class="turn-avatar-ring" :style="{ '--agent-color': speakerColor }">
            <img
              v-if="avatarUrl"
              :src="avatarUrl"
              class="turn-avatar"
              :alt="turn.speaker_name"
            />
            <div v-else class="turn-avatar-fallback" :style="{ background: speakerColor }">
              {{ initials }}
            </div>
          </div>
        </template>
        <div v-else class="turn-avatar-spacer"></div>
      </div>

      <!-- Bubble card -->
      <div class="turn-card" :style="{ '--agent-color': speakerColor }">
        <div class="turn-card-accent" :style="{ background: speakerColor }"></div>
        <div class="turn-card-body">
          <div v-if="showHeader" class="turn-card-header">
            <strong class="turn-speaker-name" :style="{ color: speakerColor }">{{ displayName }}</strong>
            <span class="turn-meta">R{{ turn.round }} &middot; {{ turn.stage }}</span>
            <span v-if="timestamp" class="turn-timestamp">{{ timestamp }}</span>
          </div>

          <!-- Collapsible thinking bubble -->
          <div v-if="thinkingText" class="thinking-section">
            <button class="thinking-toggle" @click="thinkingExpanded = !thinkingExpanded">
              <span class="thinking-chevron" :class="{ 'thinking-chevron--open': thinkingExpanded }">&#x203A;</span>
              {{ thinkingExpanded ? t('turnCard.hideReasoning') : t('turnCard.showReasoning') }}
            </button>
            <CollapseTransition>
              <div v-if="thinkingExpanded" class="thinking-bubble">
                {{ thinkingText }}
              </div>
            </CollapseTransition>
          </div>

          <!-- Message content -->
          <div :class="['turn-content', { 'turn-silent-notice': isFallbackMessage }]" v-html="renderContent(turn.content)"></div>

          <!-- Footer: observer data + TTS + timestamp -->
          <div class="turn-card-footer">
            <div v-if="observer && turn.speaker === observer.speaker" class="turn-observer">
              <span :class="['observer-pill', sentimentClass]">
                {{ t('turnCard.sentiment') }} {{ (observer.sentiment?.overall ?? 0).toFixed(2) }}
              </span>
              <span v-if="observer.claims?.length" class="observer-pill observer-claims">
                {{ t('turnCard.claims', { count: observer.claims.length }) }}
              </span>
              <span v-if="observer.behavioral_signals?.concession_offered" class="observer-pill observer-concession">
                {{ t('turnCard.concession') }}
              </span>
            </div>
            <button
              v-if="ttsEnabled() && !isMod"
              class="btn-listen"
              :title="isPlaying ? t('turnCard.stop') : t('turnCard.listen')"
              :aria-label="isPlaying ? t('turnCard.stop') : t('turnCard.listen')"
              @click="isPlaying ? stop() : speak(turn.content, { voice: stakeholder?.tts_voice })"
            >
              {{ isPlaying ? '&#9209;' : '&#128266;' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.turn-muted { opacity: 0.45; }

/* ================================================================
   MODERATOR — distinctive card with top accent stripe
   ================================================================ */
.turn-mod {
  margin-bottom: 14px;
  animation: msg-in 300ms ease;
}
.turn-mod-card {
  position: relative;
  background: var(--surface-alt);
  border-radius: var(--radius);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}
.turn-mod-accent {
  height: 3px;
  background: linear-gradient(90deg, var(--accent), var(--accent-dim));
}
.turn-mod-inner {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 16px;
}
.turn-mod-icon-wrap {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--accent-dim);
  border-radius: 50%;
}
.turn-mod-icon {
  font-size: 17px;
  line-height: 1;
}
.turn-mod-body { flex: 1; min-width: 0; }
.turn-mod-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.turn-mod-name {
  color: var(--accent);
  font-size: 13px;
  letter-spacing: 0.3px;
}
.turn-mod-content {
  font-style: italic;
  white-space: pre-wrap;
  line-height: 1.6;
  color: var(--text-muted);
  font-size: 13.5px;
}

/* ================================================================
   AGENT MESSAGE — chat bubble card with colored left accent
   ================================================================ */
.turn-bubble {
  margin-bottom: 3px;
  animation: msg-in 300ms ease;
}
.turn-bubble.turn-continuation {
  margin-bottom: 3px;
}
.turn-bubble:not(.turn-continuation) {
  margin-top: 14px;
}

.turn-bubble-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

/* Avatar with colored ring */
.turn-avatar-col {
  flex-shrink: 0;
  width: 44px;
  padding-top: 2px;
}
.turn-avatar-ring {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  padding: 2px;
  background: linear-gradient(135deg, var(--agent-color), color-mix(in srgb, var(--agent-color) 50%, transparent));
  box-shadow: 0 2px 8px color-mix(in srgb, var(--agent-color) 30%, transparent);
}
.turn-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  object-fit: cover;
  display: block;
  border: 2px solid var(--surface);
}
.turn-avatar-fallback {
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
.turn-avatar-spacer {
  width: 44px;
  height: 1px;
}

/* The card itself */
.turn-card {
  flex: 1;
  min-width: 0;
  position: relative;
  display: flex;
  background: color-mix(in srgb, var(--agent-color) 6%, var(--surface));
  border: 1px solid color-mix(in srgb, var(--agent-color) 15%, var(--border));
  border-radius: 4px var(--radius) var(--radius) var(--radius);
  box-shadow: var(--shadow-xs);
  overflow: hidden;
  transition: background var(--transition-fast), box-shadow var(--transition-fast), border-color var(--transition-fast);
}
.turn-card:hover {
  background: color-mix(in srgb, var(--agent-color) 10%, var(--surface));
  box-shadow: var(--shadow-sm);
  border-color: color-mix(in srgb, var(--agent-color) 25%, var(--border));
}

/* Colored left accent bar */
.turn-card-accent {
  width: 4px;
  flex-shrink: 0;
  border-radius: 2px 0 0 2px;
}

/* Card body */
.turn-card-body {
  flex: 1;
  min-width: 0;
  padding: 10px 14px;
}

/* Header */
.turn-card-header {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 6px;
}
.turn-speaker-name {
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.2px;
}
.turn-meta {
  font-size: 10.5px;
  color: var(--text-muted);
  opacity: 0.7;
}
.turn-timestamp {
  font-size: 10.5px;
  color: var(--text-muted);
  margin-left: auto;
  opacity: 0.6;
  transition: opacity var(--transition-fast);
}
.turn-card:hover .turn-timestamp {
  opacity: 1;
}

/* Content */
.turn-content {
  white-space: pre-wrap;
  line-height: 1.6;
  font-size: 13.5px;
  color: var(--text);
}

/* Footer */
.turn-card-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  flex-wrap: wrap;
}
.turn-observer {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.observer-pill {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  background: var(--surface-alt);
  border: 1px solid var(--border);
  font-weight: 500;
}
.observer-claims { color: var(--info); border-color: color-mix(in srgb, var(--info) 30%, var(--border)); }
.observer-concession { color: var(--success); border-color: color-mix(in srgb, var(--success) 30%, var(--border)); }

/* Sentiment semantic colors */
.sentiment-positive { color: var(--success); border-color: color-mix(in srgb, var(--success) 30%, var(--border)); }
.sentiment-negative { color: var(--danger); border-color: color-mix(in srgb, var(--danger) 30%, var(--border)); }
.sentiment-neutral  { color: var(--text-muted); }

/* Thinking section */
.thinking-section {
  margin-bottom: 8px;
}
.thinking-toggle {
  background: none;
  border: 1px solid var(--border);
  color: var(--text-muted);
  font-size: 11px;
  padding: 3px 10px;
  border-radius: var(--radius-full);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  transition: all var(--transition-fast);
}
.thinking-toggle:hover {
  background: var(--surface-alt);
  color: var(--text);
  border-color: var(--border-hover);
}
.thinking-chevron {
  display: inline-block;
  font-size: 14px;
  line-height: 1;
  transition: transform var(--transition-fast);
  transform: rotate(0deg);
}
.thinking-chevron--open {
  transform: rotate(90deg);
}
.thinking-bubble {
  background: var(--surface-alt);
  border-left: 3px solid var(--accent-dim);
  padding: 8px 12px;
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-muted);
  white-space: pre-wrap;
  line-height: 1.45;
  border-radius: 0 var(--radius-xs) var(--radius-xs) 0;
}

/* @mention pill */
:deep(.mention) {
  background: var(--accent-dim);
  color: var(--accent);
  padding: 1px 6px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
}

/* TTS button */
.btn-listen {
  background: none;
  border: 1px solid var(--border);
  cursor: pointer;
  font-size: 0.8rem;
  color: var(--text-muted);
  padding: 2px 8px;
  border-radius: var(--radius-full);
  opacity: 0.6;
  margin-left: auto;
  transition: all var(--transition-fast);
}
.btn-listen:hover { opacity: 1; background: var(--surface-alt); }

/* Fallback / silent notice styling */
.turn-silent-notice {
  font-style: italic;
  color: var(--text-muted);
  opacity: 0.65;
  border-left: 3px solid var(--border);
  padding-left: 10px;
}

/* Continuation: tighter spacing, no top-left radius */
.turn-continuation .turn-card {
  border-radius: 4px var(--radius-sm) var(--radius-sm) var(--radius);
}

/* Entry animation */
@keyframes msg-in {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}
</style>
