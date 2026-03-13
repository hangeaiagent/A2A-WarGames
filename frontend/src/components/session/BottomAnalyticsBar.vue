<script setup>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AgreementGraph from '../metrics/AgreementGraph.vue'
import ConsensusHeatmap from '../metrics/ConsensusHeatmap.vue'

const { t } = useI18n()

defineProps({
  /** Array of { slug, name, color? } */
  agents: { type: Array, default: () => [] },
  /** Observer data keyed by speaker slug */
  observerData: { type: Object, default: () => ({}) },
})

const expanded = ref(false)
const activeTab = ref('graph')

const tabs = [
  { key: 'graph', labelKey: 'bottomBar.agreementGraph' },
  { key: 'heatmap', labelKey: 'bottomBar.consensusHeatmap' },
]
</script>

<template>
  <div :class="['bottom-bar', { expanded }]">
    <!-- Toggle handle -->
    <button class="bottom-bar-handle" @click="expanded = !expanded" :title="expanded ? t('bottomBar.collapse') : t('bottomBar.expand')">
      <span class="bottom-bar-handle-icon">{{ expanded ? '▾' : '▴' }}</span>
      <span class="bottom-bar-handle-label">{{ t('bottomBar.title') }}</span>
      <span class="bottom-bar-handle-icon">{{ expanded ? '▾' : '▴' }}</span>
    </button>

    <!-- Tabbed content -->
    <div v-if="expanded" class="bottom-bar-content">
      <div class="bottom-bar-tabs">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          :class="['bottom-bar-tab', { active: activeTab === tab.key }]"
          @click="activeTab = tab.key"
        >
          {{ t(tab.labelKey) }}
        </button>
      </div>

      <div class="bottom-bar-panel">
        <AgreementGraph
          v-if="activeTab === 'graph'"
          :agents="agents"
          :observer-data="observerData"
        />
        <ConsensusHeatmap
          v-if="activeTab === 'heatmap'"
          :agents="agents"
          :observer-data="observerData"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.bottom-bar {
  flex-shrink: 0;
  border-top: 1px solid var(--border);
  background: var(--surface);
  transition: height 250ms ease;
  overflow: hidden;
}

.bottom-bar:not(.expanded) {
  height: 32px;
}

.bottom-bar.expanded {
  height: 280px;
}

.bottom-bar-handle {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  height: 32px;
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 11px;
  cursor: pointer;
  padding: 0 16px;
  transition: color 150ms ease;
}

.bottom-bar-handle:hover {
  color: var(--text);
  background: var(--surface-alt);
}

.bottom-bar-handle-icon {
  font-size: 10px;
}

.bottom-bar-handle-label {
  font-weight: 500;
  letter-spacing: 0.5px;
  text-transform: uppercase;
}

.bottom-bar-content {
  display: flex;
  flex-direction: column;
  height: calc(100% - 32px);
}

.bottom-bar-tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--border);
  padding: 0 12px;
  flex-shrink: 0;
}

.bottom-bar-tab {
  padding: 6px 14px;
  font-size: 11px;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: color 150ms, border-color 150ms;
}

.bottom-bar-tab:hover {
  color: var(--text);
}

.bottom-bar-tab.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}

.bottom-bar-panel {
  flex: 1;
  min-height: 0;
  padding: 8px 12px;
  overflow: auto;
}

@media (max-width: 768px) {
  .bottom-bar.expanded {
    height: 220px;
  }
}
</style>
