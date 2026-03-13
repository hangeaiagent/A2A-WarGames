<script setup>
import { useI18n } from 'vue-i18n'
import InjectBar from './InjectBar.vue'
import Spinner from '../common/Spinner.vue'

const { t } = useI18n()

const props = defineProps({
  status: String,
  hasEventSource: Boolean,
  canRecover: Boolean,
  contextMeterEnabled: Boolean,
  contextPercent: { type: Number, default: 0 },
  contextBarColor: { type: String, default: 'var(--success)' },
  contextUsedFormatted: String,
  contextMaxFormatted: String,
  thinkingSpeaker: Object,
  thinkingIndicatorEnabled: Boolean,
  compactConversationEnabled: Boolean,
  compactLoading: Boolean,
})

const emit = defineEmits([
  'start', 'stop', 'pause', 'resume', 'recover', 'continue',
  'inject', 'compact',
])
</script>

<template>
  <div class="session-bottombar" role="toolbar" aria-label="Session controls">
    <!-- Thinking indicator -->
    <div v-if="thinkingSpeaker && thinkingIndicatorEnabled" class="bottombar-thinking">
      <span>{{ thinkingSpeaker.speaker_name || thinkingSpeaker.speaker }} {{ t('transcript.isThinking') }}</span>
      <span class="thinking-dots">
        <span class="dot"></span>
        <span class="dot"></span>
        <span class="dot"></span>
      </span>
    </div>

    <div class="bottombar-content">
      <!-- Left: Inject Bar -->
      <div class="bottombar-inject">
        <InjectBar v-if="status === 'running'" @inject="(c, m) => emit('inject', c, m)" />
      </div>

      <!-- Center: Context Meter -->
      <div v-if="contextMeterEnabled && status === 'running'" class="bottombar-context">
        <div class="context-meter-bar">
          <div class="context-meter-fill" :style="{ width: contextPercent + '%', background: contextBarColor }"></div>
        </div>
        <span class="context-meter-label">{{ contextUsedFormatted }} / {{ contextMaxFormatted }}</span>
        <button
          v-if="compactConversationEnabled && contextPercent > 80"
          class="btn btn-ghost btn-sm compact-trigger"
          @click="emit('compact')"
          :disabled="compactLoading"
        >
          <Spinner v-if="compactLoading" size="12px" color="var(--text-muted)" />
          {{ compactLoading ? t('sessionLive.compacting') : t('sessionLive.compact') }}
        </button>
      </div>

      <!-- Right: Session Controls -->
      <div class="bottombar-controls">
        <button
          v-if="status === 'pending' || status === 'idle'"
          class="btn btn-primary"
          @click="emit('start')"
        >
          ▶ {{ t('sessionLive.startWargame') }}
        </button>
        <button
          v-if="status === 'running'"
          class="btn btn-danger btn-sm"
          @click="emit('stop')"
        >
          ■ {{ t('sessionLive.stop') }}
        </button>
        <button
          v-if="status === 'running' && hasEventSource"
          class="btn btn-warn btn-sm"
          @click="emit('pause')"
        >
          ⏸ {{ t('sessionLive.pause') }}
        </button>
        <button
          v-if="status === 'paused' && hasEventSource"
          class="btn btn-primary btn-sm"
          @click="emit('resume')"
        >
          ▶ {{ t('sessionLive.resume') }}
        </button>
        <button
          v-if="canRecover || status === 'disconnected'"
          class="btn btn-primary btn-sm"
          @click="emit('recover')"
        >
          🔄 {{ t(status === 'disconnected' ? 'sessionLive.reconnect' : 'sessionLive.recover') }}
        </button>
        <button
          v-if="['stopped', 'complete', 'errored', 'failed'].includes(status)"
          class="btn btn-primary btn-sm"
          @click="emit('continue')"
        >
          ▶ {{ t('sessionLive.continue', 'Continue') }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.session-bottombar {
  flex-shrink: 0;
  background: color-mix(in srgb, var(--surface) 85%, transparent);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-top: 1px solid var(--border);
  padding: var(--space-2) var(--space-4);
  box-shadow: 0 -4px 16px rgba(0, 0, 0, 0.15);
  z-index: 30;
}

.bottombar-thinking {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) 0;
  font-size: 12px;
  color: var(--text-muted);
  font-style: italic;
}

.bottombar-content {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.bottombar-inject {
  flex: 1;
  min-width: 0;
}

.bottombar-context {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: 11px;
  color: var(--text-muted);
  flex-shrink: 0;
}

.context-meter-bar {
  width: 80px;
  height: 8px;
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

.compact-trigger {
  font-size: 11px;
  padding: 2px 8px;
}

.bottombar-controls {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
}

@media (max-width: 768px) {
  .bottombar-content {
    flex-wrap: wrap;
  }
  .bottombar-inject {
    flex-basis: 100%;
  }
  .bottombar-context {
    flex: 1;
  }
}
</style>
