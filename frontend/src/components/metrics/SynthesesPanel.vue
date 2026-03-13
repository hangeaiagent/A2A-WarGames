<script setup>
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

defineProps({ syntheses: { type: Array, default: () => [] } })
</script>

<template>
  <div v-if="syntheses.length" class="panel-box">
    <div class="panel-title">{{ t('metrics.roundSyntheses') }}</div>
    <div v-for="(s, i) in syntheses" :key="i" class="synth-entry">
      <div class="synth-round-header">
        {{ t('metrics.roundNumber', { round: s.round }) }} {{ s.is_final ? t('metrics.final') : '' }}
      </div>
      <div class="synth-content">{{ s.content }}</div>
    </div>
  </div>
</template>

<style scoped>
.synth-entry {
  background: var(--surface-alt);
  padding: var(--space-3);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-xs);
  margin-bottom: var(--space-3);
}

.synth-entry:last-child {
  margin-bottom: 0;
}

.synth-round-header {
  font-family: var(--font-display);
  font-size: 11px;
  font-weight: 600;
  color: var(--accent);
  margin-bottom: 6px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--accent-dim, rgba(233,69,96,0.3));
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.synth-content {
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  color: var(--text);
}
</style>
