<script setup>
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSessionStore } from '../../stores/sessions'

const { t } = useI18n()

const props = defineProps({
  sessionId: { type: Number, required: true }
})

const sessionStore = useSessionStore()
const collapsed = ref(false)

const threads = computed(() => sessionStore.privateThreads || [])
const activeCount = computed(() => threads.value.filter(t => t.status === 'open').length)

function toggleCollapsed() {
  collapsed.value = !collapsed.value
}

function threadStatusClass(status) {
  if (status === 'declined') return 'whisper-declined'
  if (status === 'closed') return 'whisper-closed'
  return 'whisper-open'
}
</script>

<template>
  <div class="whisper-panel" :class="{ 'whisper-panel--collapsed': collapsed }">
    <button
      class="whisper-header"
      type="button"
      :aria-expanded="!collapsed"
      aria-controls="whisper-body"
      @click="toggleCollapsed"
      @keydown.enter.prevent="toggleCollapsed"
      @keydown.space.prevent="toggleCollapsed"
    >
      <span class="whisper-icon">🔒</span>
      <span class="whisper-title">{{ t('whisperPanel.title') }}</span>
      <span v-if="activeCount > 0" class="whisper-badge">{{ activeCount }}</span>
      <span class="whisper-toggle" :class="{ 'whisper-toggle--up': collapsed }" aria-hidden="true">▼</span>
    </button>

    <div id="whisper-body" class="whisper-body" :class="{ 'whisper-body--hidden': collapsed }">
      <div v-if="threads.length === 0" class="whisper-empty">
        {{ t('whisperPanel.noThreads') }}
      </div>

      <div
        v-for="thread in threads"
        :key="thread.thread_id"
        class="whisper-thread"
        :class="threadStatusClass(thread.status)"
      >
        <div class="whisper-thread-header">
          <span class="whisper-agents">
            {{ thread.initiator_name }} ↔ {{ thread.target_name }}
          </span>
          <span class="whisper-round">{{ t('whisperPanel.round', { round: thread.round }) }}</span>
          <span class="whisper-status">{{ thread.status?.toUpperCase() }}</span>
        </div>

        <div class="whisper-messages">
          <div
            v-for="(msg, idx) in thread.messages"
            :key="idx"
            class="whisper-msg"
          >
            <strong>{{ msg.speaker_name }}:</strong> {{ msg.content }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ── Panel container ──────────────────────────────────────── */
.whisper-panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin: var(--space-3) 0;
  overflow: hidden;
  box-shadow: var(--shadow-sm);
  transition: box-shadow var(--transition-fast);
}

/* ── Header ───────────────────────────────────────────────── */
.whisper-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  cursor: pointer;
  user-select: none;
  background: linear-gradient(135deg, var(--surface) 0%, var(--surface-alt) 100%);
  transition: background var(--transition-fast);
  width: 100%;
  border: none;
  border-radius: 0;
  font: inherit;
  color: inherit;
  text-align: left;
}

.whisper-header:hover {
  background: linear-gradient(135deg, var(--surface-hover) 0%, var(--surface-alt) 100%);
}

.whisper-icon {
  font-size: 14px;
  flex-shrink: 0;
}

.whisper-title {
  font-weight: 600;
  font-size: 0.9rem;
  color: var(--text-muted);
  flex: 1;
}

/* ── Badge ────────────────────────────────────────────────── */
.whisper-badge {
  background: var(--whisper);
  color: #fff;
  border-radius: var(--radius-full);
  padding: 2px var(--space-2);
  font-size: 0.75rem;
  font-weight: 700;
  line-height: 1.4;
}

/* ── Toggle arrow ─────────────────────────────────────────── */
.whisper-toggle {
  color: var(--text-muted);
  font-size: 0.75rem;
  transition: transform var(--transition-base);
  display: inline-block;
}

.whisper-toggle--up {
  transform: rotate(180deg);
}

/* ── Body (collapse animation) ────────────────────────────── */
.whisper-body {
  padding: var(--space-2) var(--space-3);
  max-height: 320px;
  overflow-y: auto;
  opacity: 1;
  transition:
    max-height var(--transition-slow),
    opacity var(--transition-base),
    padding var(--transition-base);
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}

.whisper-body::-webkit-scrollbar {
  width: 4px;
}

.whisper-body::-webkit-scrollbar-track {
  background: transparent;
}

.whisper-body::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: var(--radius-full);
}

.whisper-body--hidden {
  max-height: 0;
  opacity: 0;
  padding-top: 0;
  padding-bottom: 0;
  overflow: hidden;
}

/* ── Empty state ──────────────────────────────────────────── */
.whisper-empty {
  color: var(--text-muted);
  font-size: 0.85rem;
  padding: var(--space-2) 0;
}

/* ── Thread cards ─────────────────────────────────────────── */
.whisper-thread {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  margin-bottom: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--bg);
  box-shadow: var(--shadow-xs);
  transition:
    border-color var(--transition-fast),
    box-shadow var(--transition-fast);
}

.whisper-thread:hover {
  box-shadow: var(--shadow-sm);
}

.whisper-thread.whisper-declined {
  opacity: 0.5;
  border-color: color-mix(in srgb, var(--danger) 40%, var(--border));
}

.whisper-thread.whisper-closed {
  border-color: color-mix(in srgb, var(--success) 35%, var(--border));
}

.whisper-thread.whisper-open {
  border-color: var(--whisper);
}

/* ── Thread header ────────────────────────────────────────── */
.whisper-thread-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
  flex-wrap: wrap;
}

.whisper-agents {
  font-weight: 600;
  font-size: 0.85rem;
  color: var(--whisper-text);
}

.whisper-round {
  color: var(--text-muted);
  font-size: 0.75rem;
}

.whisper-status {
  font-size: 0.7rem;
  color: var(--text-muted);
  margin-left: auto;
  letter-spacing: 0.04em;
}

/* ── Thread messages ──────────────────────────────────────── */
.whisper-messages {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.whisper-msg {
  font-size: 0.82rem;
  color: var(--text);
  padding: var(--space-1) var(--space-1);
  border-bottom: 1px solid var(--border);
  line-height: 1.4;
  border-radius: var(--radius-xs);
  transition: background var(--transition-fast);
}

.whisper-msg:hover {
  background: var(--surface-hover);
}

.whisper-msg:last-child {
  border-bottom: none;
}
</style>
