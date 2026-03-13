<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps({ agents: { type: Array, default: () => [] } })

function sentimentColor(val) {
  if (val >= 0.3) return 'var(--success)'
  if (val <= -0.3) return 'var(--danger)'
  return 'var(--warn)'
}

function sentimentLabel(val) {
  if (val >= 0.5) return t('sentimentLabels.supportive')
  if (val >= 0.2) return t('sentimentLabels.cautiousPlus')
  if (val >= -0.2) return t('sentimentLabels.neutral')
  if (val >= -0.5) return t('sentimentLabels.opposed')
  return t('sentimentLabels.hostile')
}

function sentimentPillBg(val) {
  if (val >= 0.3) return 'color-mix(in srgb, var(--success) 12%, transparent)'
  if (val <= -0.3) return 'color-mix(in srgb, var(--danger) 12%, transparent)'
  return 'color-mix(in srgb, var(--warn) 12%, transparent)'
}

const sorted = computed(() => [...props.agents].sort((a, b) => b.overall - a.overall))
</script>

<template>
  <div class="panel-box">
    <div class="panel-title">{{ t('metrics.agentSentiment') }}</div>
    <div
      v-if="sorted.length === 0"
      class="sp-waiting"
    >{{ t('metrics.waitingForData') }}</div>
    <div
      v-for="(a, index) in sorted"
      :key="a.slug"
      class="sp-row"
      :style="{ animationDelay: `${index * 60}ms` }"
    >
      <span
        class="sp-dot"
        :style="{
          background: sentimentColor(a.overall),
          boxShadow: `0 0 6px ${sentimentColor(a.overall)}50`,
        }"
      />
      <span class="sp-name">{{ a.name }}</span>
      <span
        class="sp-value"
        :style="{
          color: sentimentColor(a.overall),
          background: sentimentPillBg(a.overall),
        }"
      >
        {{ a.overall >= 0 ? '+' : '' }}{{ a.overall.toFixed(2) }}
      </span>
      <span class="sp-label">
        {{ sentimentLabel(a.overall) }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.sp-waiting {
  color: var(--text-muted);
  font-size: 12px;
  font-style: italic;
}

.sp-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: var(--space-2);
  border-radius: var(--radius-sm);
  transition: background var(--transition-fast);
  animation: sp-slide-in 300ms ease both;
}

@keyframes sp-slide-in {
  from { opacity: 0; transform: translateX(-8px); }
  to   { opacity: 1; transform: translateX(0); }
}

.sp-row:hover {
  background: var(--surface-hover);
}

.sp-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
  transition: background 0.5s ease, box-shadow 0.5s ease;
}

.sp-name {
  flex: 1;
  font-size: 13px;
}

.sp-value {
  font-size: 12px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  transition: color 0.4s ease, background 0.4s ease;
}

.sp-label {
  font-size: 11px;
  color: var(--text-muted);
  width: 70px;
  text-align: right;
}
</style>
