<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps({ value: { type: Number, default: 0 } })

const color = computed(() => {
  if (props.value >= 0.6) return 'var(--success)'
  if (props.value >= 0.3) return 'var(--warn)'
  return 'var(--danger)'
})

const pct = computed(() => Math.round(props.value * 100))
const isHighConsensus = computed(() => pct.value >= 80)
</script>

<template>
  <div class="panel-box gauge-wrap">
    <div class="panel-title">{{ t('metrics.consensusScore') }}</div>
    <div class="gauge-row">
      <div class="gauge-track">
        <div
          class="gauge-fill"
          :class="{ 'gauge-fill--high': isHighConsensus }"
          :style="{
            width: pct + '%',
            background: color,
            boxShadow: `0 0 8px ${color}40`,
          }"
        />
      </div>
      <span
        class="gauge-pct"
        :style="{ color }"
      >{{ pct }}%</span>
    </div>
  </div>
</template>

<style scoped>
.gauge-wrap {
  animation: slide-up 300ms ease both;
}

.gauge-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.gauge-track {
  flex: 1;
  height: 12px;
  background: var(--border);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.gauge-fill {
  height: 100%;
  border-radius: var(--radius-full);
  transition: width 0.5s ease;
  animation: gauge-grow 600ms ease both;
}

.gauge-pct {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 700;
  min-width: 44px;
  text-align: right;
}

@keyframes gauge-grow {
  from { width: 0% !important; }
}

@keyframes gauge-pulse {
  0%, 100% { box-shadow: 0 0 8px var(--success, #4caf50); }
  50% { box-shadow: 0 0 18px var(--success, #4caf50), 0 0 28px var(--success, #4caf50); }
}

.gauge-fill--high {
  animation: gauge-pulse 2s ease-in-out infinite;
}

@keyframes slide-up {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}
</style>
