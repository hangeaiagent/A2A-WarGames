<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps({
  items: { type: Array, default: () => [] },    // from GET /api/sessions/{id}/voting-summary
  agents: { type: Array, default: () => [] },   // [{slug, name}] for column ordering
})

// Use CSS variable names so colors respond to theme changes
const stanceColorVar = {
  agree:   'var(--success)',
  oppose:  'var(--danger)',
  neutral: 'var(--text-muted)',
  abstain: 'var(--border-hover)',
}
const stanceLabel = {
  agree:   'A',
  oppose:  'O',
  neutral: 'N',
  abstain: '–',
}
const trendIcon = {
  converging: '↑',
  diverging:  '↓',
  stable:     '→',
  no_data:    '',
}
const trendColorVar = {
  converging: 'var(--success)',
  diverging:  'var(--danger)',
  stable:     'var(--text-muted)',
  no_data:    'transparent',
}

// Latest stance per agent per item
function latestStance(agentHistory) {
  if (!agentHistory || agentHistory.length === 0) return null
  return agentHistory[agentHistory.length - 1]
}

// Did the agent change stance in the last round?
function stanceChanged(agentHistory) {
  if (!agentHistory || agentHistory.length < 2) return false
  const last = agentHistory[agentHistory.length - 1]
  const prev = agentHistory[agentHistory.length - 2]
  return last.stance !== prev.stance
}

const agentList = computed(() =>
  props.agents.length > 0
    ? props.agents
    : Object.keys(props.items[0]?.agents || {}).map(s => ({ slug: s, name: s }))
)
</script>

<template>
  <div class="voting-matrix" v-if="items.length > 0">
    <div class="vm-title">{{ t('votingMatrix.title') }}</div>

    <div class="vm-table-wrap">
      <table class="vm-table">
        <thead>
          <tr>
            <th class="vm-th vm-th-agent">{{ t('votingMatrix.agent') }}</th>
            <th v-for="item in items" :key="item.key" class="vm-th">
              <span class="vm-item-label" :title="item.description">{{ item.label }}</span>
              <span
                class="vm-trend"
                :style="{ color: trendColorVar[item.consensus_trend] }"
                :title="item.consensus_trend"
              >{{ trendIcon[item.consensus_trend] }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="agent in agentList" :key="agent.slug">
            <td class="vm-td vm-td-agent">{{ agent.name || agent.slug }}</td>
            <td v-for="item in items" :key="item.key" class="vm-td vm-td-stance">
              <template v-if="item.agents[agent.slug]">
                <span
                  class="vm-chip"
                  :style="{ background: stanceColorVar[latestStance(item.agents[agent.slug])?.stance] }"
                  :title="latestStance(item.agents[agent.slug])?.stance"
                >{{ stanceLabel[latestStance(item.agents[agent.slug])?.stance] }}</span>
                <span
                  v-if="stanceChanged(item.agents[agent.slug])"
                  class="vm-delta"
                  title="Stance changed last round"
                >!</span>
              </template>
              <span v-else class="vm-chip vm-chip-empty" title="No vote yet">·</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Legend -->
    <div class="vm-legend">
      <span v-for="(colorVar, stance) in stanceColorVar" :key="stance" class="vm-legend-item">
        <span class="vm-chip vm-chip-sm" :style="{ background: colorVar }">{{ stanceLabel[stance] }}</span>
        {{ stance }}
      </span>
      <span class="vm-legend-item"><span class="vm-delta">!</span> {{ t('votingMatrix.changed') }}</span>
    </div>
  </div>

  <div v-else class="vm-empty">
    {{ t('votingMatrix.empty') }}
  </div>
</template>

<style scoped>
.voting-matrix {
  margin: 12px 0;
}

.vm-title {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text-muted, #888);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: var(--space-2);
}

.vm-table-wrap {
  border-radius: var(--radius-sm);
  overflow: hidden;
  border: 1px solid var(--border, #333);
}

.vm-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.78rem;
}

.vm-th {
  text-align: center;
  padding: 6px 6px;
  color: var(--text-muted, #aaa);
  font-weight: 500;
  border-bottom: 1px solid var(--border, #333);
  white-space: nowrap;
  background: var(--surface-alt);
}

.vm-th-agent {
  text-align: left;
  min-width: 80px;
}

.vm-item-label {
  display: block;
  max-width: 80px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: default;
}

.vm-trend {
  font-size: 0.75rem;
  font-weight: 700;
}

.vm-td {
  padding: 4px 6px;
  border-bottom: 1px solid var(--border, #222);
  text-align: center;
  vertical-align: middle;
  transition: background-color 0.4s ease;
}

.vm-td:hover {
  background-color: var(--surface-hover);
}

.vm-td-agent {
  text-align: left;
  color: var(--text, #e0e0e0);
  font-weight: 500;
}

.vm-td-stance {
  position: relative;
}

.vm-chip {
  display: inline-block;
  width: 24px;
  height: 24px;
  line-height: 24px;
  border-radius: var(--radius-xs);
  text-align: center;
  font-size: 0.7rem;
  font-weight: 700;
  color: #fff;
  transition: transform var(--transition-fast);
  cursor: default;
}

.vm-chip:hover {
  transform: scale(1.2);
  box-shadow: 0 0 6px currentColor;
  z-index: 2;
  position: relative;
}

.vm-chip-sm {
  width: 16px;
  height: 16px;
  line-height: 16px;
  font-size: 0.65rem;
}

.vm-chip-empty {
  background: var(--surface-alt);
  color: var(--text-muted);
}

.vm-delta {
  font-size: 0.6rem;
  color: var(--warn);
  font-weight: 700;
  vertical-align: super;
}

.vm-legend {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-top: var(--space-2);
  font-size: 0.7rem;
  color: var(--text-muted, #888);
}

.vm-legend-item {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.vm-empty {
  color: var(--text-muted, #666);
  font-size: 0.82rem;
  padding: 8px 0;
}
</style>
