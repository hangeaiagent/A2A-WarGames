<script setup>
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { VueDraggable } from 'vue-draggable-plus'
import AgentCard from './AgentCard.vue'
import EmptyState from '../common/EmptyState.vue'
import SkeletonLoader from '../common/SkeletonLoader.vue'
import Spinner from '../common/Spinner.vue'

const { t } = useI18n()

const props = defineProps({
  participants: { type: Array, default: () => [] },
  observerData: { type: Object, default: () => ({}) },
  agentOverrides: { type: Object, default: () => ({}) },
  analyticsRounds: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  thinkingSpeaker: { type: Object, default: null },
  sessionId: { type: [Number, String], default: null },
})
const emit = defineEmits(['mute', 'update-override', 'reorder'])

// Reactive sorted list that can be reordered by dragging
const sortedParticipants = ref([])

// Sync participants → sortedParticipants, respecting saved order
watch(() => props.participants, (newVal) => {
  if (!newVal.length) {
    sortedParticipants.value = []
    return
  }
  // Try to restore saved order from localStorage
  const storageKey = props.sessionId ? `agent-order-${props.sessionId}` : null
  let savedOrder = null
  if (storageKey) {
    try {
      savedOrder = JSON.parse(localStorage.getItem(storageKey))
    } catch { /* ignore */ }
  }
  if (savedOrder && Array.isArray(savedOrder)) {
    const map = Object.fromEntries(newVal.map(p => [p.slug, p]))
    const ordered = savedOrder
      .filter(slug => map[slug])
      .map(slug => map[slug])
    // Append any new participants not in saved order
    const remaining = newVal.filter(p => !savedOrder.includes(p.slug))
    sortedParticipants.value = [...ordered, ...remaining]
  } else {
    sortedParticipants.value = [...newVal]
  }
}, { immediate: true })

function onDragEnd() {
  // Persist order
  const slugOrder = sortedParticipants.value.map(p => p.slug)
  const storageKey = props.sessionId ? `agent-order-${props.sessionId}` : null
  if (storageKey) {
    localStorage.setItem(storageKey, JSON.stringify(slugOrder))
  }
  emit('reorder', slugOrder)
}

function getTurnsSpoken(slug) {
  const latest = props.analyticsRounds[props.analyticsRounds.length - 1]
  return latest?.turns_spoken?.[slug] ?? 0
}
</script>

<template>
  <div class="agent-panel">
    <div class="section-title agent-panel__title">{{ t('agentPanel.agents') }}</div>

    <!-- Loading header row with spinner -->
    <div v-if="loading && sortedParticipants.length === 0" class="agent-panel__loading-header">
      <Spinner size="16px" color="var(--accent)" />
      <span class="agent-panel__loading-label">{{ t('agentPanel.loadingAgents') }}</span>
    </div>

    <!-- Skeleton placeholders while loading -->
    <div v-if="loading && sortedParticipants.length === 0" class="agent-panel__skeletons">
      <div v-for="n in 3" :key="n" class="agent-panel__skeleton-card">
        <SkeletonLoader height="48px" rounded />
        <SkeletonLoader height="12px" :count="2" />
      </div>
    </div>

    <!-- Empty state when not loading and no participants -->
    <EmptyState
      v-else-if="!loading && sortedParticipants.length === 0"
      icon="👥"
      :title="t('agentPanel.noParticipants')"
    />

    <!-- Draggable agent cards -->
    <VueDraggable
      v-else
      v-model="sortedParticipants"
      :animation="200"
      handle=".agent-drag-handle"
      ghost-class="agent-card--ghost"
      drag-class="agent-card--dragging"
      @end="onDragEnd"
      class="agent-panel__list"
    >
      <AgentCard
        v-for="agent in sortedParticipants"
        :key="agent.slug"
        :agent="agent"
        :observer="observerData[agent.slug]"
        :override="agentOverrides[agent.slug]"
        :turns-spoken="getTurnsSpoken(agent.slug)"
        :is-thinking="thinkingSpeaker?.speaker === agent.slug"
        @mute="emit('mute', agent.slug)"
        @update-override="(o) => emit('update-override', agent.slug, o)"
      />
    </VueDraggable>
  </div>
</template>

<style scoped>
.agent-panel {
  height: 100%;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}

.agent-panel::-webkit-scrollbar {
  width: 4px;
}

.agent-panel::-webkit-scrollbar-track {
  background: transparent;
}

.agent-panel::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: var(--radius-full);
}

.agent-panel::-webkit-scrollbar-thumb:hover {
  background: var(--border-hover);
}

.agent-panel__title {
  margin-top: 0;
}

.agent-panel__list {
  display: flex;
  flex-direction: column;
}

/* ── Loading header row ───────────────────────────────────── */
.agent-panel__loading-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) 0 var(--space-3);
}
.agent-panel__loading-label {
  font-size: 12px;
  color: var(--text-muted);
}

/* ── Skeleton cards ───────────────────────────────────────── */
.agent-panel__skeletons {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.agent-panel__skeleton-card {
  padding: var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
}

/* ── Drag ghost & dragging states ─────────────────────────── */
:deep(.agent-card--ghost) {
  opacity: 0.4;
  border: 2px dashed var(--accent);
  background: var(--accent-dim);
}

:deep(.agent-card--dragging) {
  box-shadow: var(--shadow-lg);
  transform: rotate(1deg);
}
</style>
