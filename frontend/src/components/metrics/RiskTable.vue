<script setup>
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

defineProps({ agents: { type: Array, default: () => [] } })

function riskColor(level) {
  if (level === 'HIGH') return 'var(--danger)'
  if (level === 'MEDIUM') return 'var(--warn)'
  return 'var(--success)'
}

function riskBg(level) {
  if (level === 'HIGH') return 'color-mix(in srgb, var(--danger) 15%, transparent)'
  if (level === 'MEDIUM') return 'color-mix(in srgb, var(--warn) 15%, transparent)'
  return 'color-mix(in srgb, var(--success) 15%, transparent)'
}
</script>

<template>
  <div v-if="agents.length" class="panel-box">
    <div class="panel-title">{{ t('metrics.riskAssessment') }}</div>
    <div v-for="(r, i) in agents" :key="i" class="rt-row">
      <span class="rt-name">{{ r.name }}</span>
      <div class="rt-track">
        <div
          class="rt-fill"
          :style="{
            width: (r.score * 10) + '%',
            background: riskColor(r.level),
            boxShadow: `0 0 6px ${riskColor(r.level)}60`,
          }"
        />
      </div>
      <span
        class="rt-badge"
        :style="{
          color: riskColor(r.level),
          background: riskBg(r.level),
        }"
      >{{ r.level }}</span>
    </div>
  </div>
</template>

<style scoped>
.rt-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: var(--space-2);
  border-radius: var(--radius-sm);
  transition: background var(--transition-fast);
}

.rt-row:hover {
  background: var(--surface-hover);
}

.rt-name {
  flex: 1;
  font-size: 13px;
}

.rt-track {
  width: 100px;
  height: 8px;
  background: var(--border);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.rt-fill {
  height: 100%;
  border-radius: var(--radius-full);
  transition: width var(--transition-slow);
}

.rt-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  width: 56px;
  text-align: center;
  letter-spacing: 0.03em;
}
</style>
