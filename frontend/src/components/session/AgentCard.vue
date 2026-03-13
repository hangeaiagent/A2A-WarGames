<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import Spinner from '../common/Spinner.vue'

const { t } = useI18n()

const props = defineProps({
  agent: Object,
  observer: Object,
  override: Object,
  turnsSpoken: { type: Number, default: 0 },
  isThinking: { type: Boolean, default: false },
})
const emit = defineEmits(['mute', 'update-override'])

const isMuted = computed(() => props.override?.is_silenced)

const sentiment = computed(() => props.observer?.sentiment?.overall ?? null)

function sentimentColor(val) {
  if (val === null) return 'var(--border)'
  if (val >= 0.3) return 'var(--success)'
  if (val <= -0.3) return 'var(--danger)'
  return 'var(--warn)'
}

function sentimentBg(val) {
  if (val === null) return 'transparent'
  if (val >= 0.3) return 'color-mix(in srgb, var(--success) 15%, transparent)'
  if (val <= -0.3) return 'color-mix(in srgb, var(--danger) 15%, transparent)'
  return 'color-mix(in srgb, var(--warn) 12%, transparent)'
}

const attitudeCssVars = {
  founder: 'var(--attitude-founder, #0f3460)',
  enthusiast: 'var(--attitude-enthusiast, #27ae60)',
  conditional: 'var(--attitude-conditional, #e67e22)',
  critical: 'var(--attitude-critical, #c0392b)',
  strategic: 'var(--attitude-strategic, #2980b9)',
  neutral: 'var(--attitude-neutral, #888888)',
}

const avatarBorderColor = computed(() => {
  const att = props.agent.attitude || 'neutral'
  return attitudeCssVars[att] || attitudeCssVars.neutral
})

const avatarGlowStyle = computed(() => ({
  boxShadow: `0 0 0 2px ${avatarBorderColor.value}, 0 0 10px ${avatarBorderColor.value}30`,
  border: `3px solid ${avatarBorderColor.value}`,
}))

const avatarUrl = computed(() => props.agent.avatar_url || null)

const avatarInitial = computed(() => {
  const name = props.agent.name || ''
  return name.charAt(0).toUpperCase()
})

const isSpeaking = computed(() => props.observer?.is_speaking ?? false)
</script>

<template>
  <div
    class="agent-card"
    :class="{
      'agent-card--muted': isMuted,
      'agent-card--speaking': isSpeaking,
      'agent-card--thinking': isThinking,
    }"
  >
    <!-- Drag handle -->
    <div class="agent-drag-handle" title="Drag to reorder">
      <svg width="10" height="16" viewBox="0 0 10 16" fill="currentColor">
        <circle cx="2" cy="2" r="1.5"/><circle cx="8" cy="2" r="1.5"/>
        <circle cx="2" cy="8" r="1.5"/><circle cx="8" cy="8" r="1.5"/>
        <circle cx="2" cy="14" r="1.5"/><circle cx="8" cy="14" r="1.5"/>
      </svg>
    </div>

    <!-- Thinking indicator — subtle corner badge, not a full overlay -->
    <div v-if="isThinking" class="agent-thinking-badge">
      <Spinner size="14px" :color="agent.color || 'var(--accent)'" />
    </div>

    <!-- Avatar -->
    <div class="agent-avatar-wrap">
      <img
        v-if="avatarUrl"
        :src="avatarUrl"
        :alt="agent.name"
        class="agent-avatar"
        :style="avatarGlowStyle"
      />
      <div
        v-else
        class="agent-avatar agent-avatar--initials"
        :style="{
          background: agent.color || '#888',
          ...avatarGlowStyle,
        }"
      >
        {{ avatarInitial }}
      </div>
    </div>

    <!-- Name row -->
    <div class="agent-name-row">
      <span class="agent-dot" :style="{ background: agent.color || '#888' }" />
      <span class="agent-name">{{ agent.name }}</span>
      <span
        v-if="sentiment !== null"
        class="agent-sentiment"
        :style="{
          color: sentimentColor(sentiment),
          background: sentimentBg(sentiment),
        }"
      >
        {{ sentiment >= 0 ? '+' : '' }}{{ sentiment.toFixed(2) }}
      </span>
    </div>

    <!-- Turns + mute row -->
    <div class="agent-meta-row">
      <span class="agent-turns">{{ t('agentCard.turns', { count: turnsSpoken }) }}</span>
      <button
        :class="['btn', isMuted ? 'btn-warn' : 'btn-ghost', 'agent-mute-btn']"
        @click="emit('mute')"
      >
        {{ isMuted ? t('agentCard.muted') : t('agentCard.mute') }}
      </button>
    </div>

    <!-- Token budget slider -->
    <div class="agent-slider-group">
      <label class="agent-slider-label" :title="t('agentCard.tokenBudgetTooltip')">
        {{ t('agentCard.tokenBudget', { value: override?.max_tokens ?? 1024 }) }}
      </label>
      <input
        type="range" min="128" max="2048" step="128"
        :value="override?.max_tokens ?? 1024"
        :disabled="isMuted"
        @input="emit('update-override', { max_tokens: parseInt($event.target.value) })"
        class="agent-range"
        :title="t('agentCard.tokenBudgetTooltip')"
      />
    </div>

    <!-- Priority slider -->
    <div class="agent-slider-group">
      <label class="agent-slider-label" :title="t('agentCard.priorityTooltip')">
        {{ t('agentCard.priority', { value: (override?.speaking_priority ?? 1.0).toFixed(1) }) }}
      </label>
      <input
        type="range" min="0" max="2" step="0.1"
        :value="override?.speaking_priority ?? 1.0"
        :disabled="isMuted"
        @input="emit('update-override', { speaking_priority: parseFloat($event.target.value) })"
        class="agent-range"
        :title="t('agentCard.priorityTooltip')"
      />
    </div>
  </div>
</template>

<style scoped>
/* ── Card container ───────────────────────────────────────── */
.agent-card {
  position: relative;
  padding: var(--space-3);
  padding-top: calc(var(--space-3) + 4px);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: var(--space-2);
  background: var(--surface);
  opacity: 1;
  box-shadow: var(--shadow-xs);
  transition:
    transform var(--transition-fast),
    box-shadow var(--transition-fast),
    border-color var(--transition-fast),
    opacity var(--transition-fast);
}

/* ── Drag handle ─────────────────────────────────────────── */
.agent-drag-handle {
  position: absolute;
  top: 4px;
  left: 50%;
  transform: translateX(-50%);
  cursor: grab;
  color: var(--border);
  opacity: 0.4;
  transition: opacity var(--transition-fast), color var(--transition-fast);
  padding: 2px 8px;
  display: flex;
  align-items: center;
}
.agent-drag-handle:hover {
  opacity: 1;
  color: var(--text-muted);
}
.agent-drag-handle:active {
  cursor: grabbing;
}

.agent-card:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-sm);
  border-color: var(--border-hover);
}

.agent-card--muted {
  background: var(--surface-hover);
  opacity: 0.6;
}

/* ── Thinking state ──────────────────────────────────────── */
.agent-card--thinking {
  border-color: var(--accent);
  box-shadow: 0 0 12px var(--accent-glow);
}

.agent-thinking-badge {
  position: absolute;
  top: 6px;
  right: 6px;
  z-index: 5;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--surface);
  border: 1px solid var(--accent);
  box-shadow: 0 0 8px var(--accent-glow, rgba(233,69,96,0.2));
  animation: fade-in 200ms ease;
}

/* ── Speaking glow ────────────────────────────────────────── */
.agent-card--speaking .agent-avatar {
  animation: speaking-glow 1.6s ease-in-out infinite;
}

@keyframes speaking-glow {
  0%, 100% {
    filter: drop-shadow(0 0 4px currentColor);
    opacity: 1;
  }
  50% {
    filter: drop-shadow(0 0 10px currentColor);
    opacity: 0.88;
  }
}

/* ── Avatar ───────────────────────────────────────────────── */
.agent-avatar-wrap {
  display: flex;
  justify-content: center;
  margin-bottom: var(--space-2);
}

.agent-avatar {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  object-fit: cover;
  flex-shrink: 0;
  transition: box-shadow var(--transition-fast);
}

.agent-avatar--initials {
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 18px;
  color: #fff;
}

/* ── Name row ─────────────────────────────────────────────── */
.agent-name-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.agent-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.agent-name {
  flex: 1;
  font-weight: 600;
  font-size: 13px;
  color: var(--text);
}

.agent-sentiment {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: var(--radius-full);
  line-height: 1;
  transition: background var(--transition-fast);
}

/* ── Meta row (turns + mute) ──────────────────────────────── */
.agent-meta-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-top: var(--space-1);
}

.agent-turns {
  font-size: 11px;
  color: var(--text-muted);
}

.agent-mute-btn {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  margin-left: auto;
}

/* ── Slider groups ────────────────────────────────────────── */
.agent-slider-group {
  margin-top: var(--space-2);
}

.agent-slider-label {
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: 2px;
}

.agent-range {
  width: 100%;
}
</style>
