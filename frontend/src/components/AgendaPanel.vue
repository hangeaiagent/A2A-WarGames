<template>
  <div class="agenda-panel" v-if="agenda.items && agenda.items.length">
    <div class="agenda-header">
      <div class="agenda-icon">📋</div>
      <div>
        <h3 class="panel-title">{{ t('metrics.agenda') }}</h3>
        <div class="agenda-subtitle">{{ t('metrics.agendaSubtitle') }}</div>
      </div>
    </div>

    <div class="agenda-items">
      <div v-for="(item, idx) in agenda.items" :key="item.key" class="agenda-item">
        <div class="item-header">
          <span class="item-number">{{ idx + 1 }}</span>
          <div class="item-content">
            <div class="item-label">{{ item.label }}</div>
            <div v-if="item.description" class="item-description">{{ item.description }}</div>
          </div>
        </div>

        <div class="vote-bar-wrap">
          <div class="vote-bar">
            <div
              class="bar-segment agree"
              :style="{ width: pct(item.tally, 'agree') + '%' }"
              :title="`${t('metrics.agendaAgree')}: ${item.tally.agree}`"
            />
            <div
              class="bar-segment oppose"
              :style="{ width: pct(item.tally, 'oppose') + '%' }"
              :title="`${t('metrics.agendaOppose')}: ${item.tally.oppose}`"
            />
            <div
              class="bar-segment neutral"
              :style="{ width: pct(item.tally, 'neutral') + '%' }"
              :title="`${t('metrics.agendaNeutral')}: ${item.tally.neutral}`"
            />
          </div>
        </div>

        <div class="vote-counts">
          <span class="pill agree">&#10003; {{ item.tally.agree }}</span>
          <span class="pill oppose">&#10007; {{ item.tally.oppose }}</span>
          <span class="pill neutral">~ {{ item.tally.neutral }}</span>
          <span v-if="totalVotes(item.tally) > 0" class="vote-total">{{ totalVotes(item.tally) }} {{ t('metrics.agendaVotes') }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps({ agenda: { type: Object, default: () => ({ items: [] }) } })

function pct(tally, key) {
  const total = (tally.agree || 0) + (tally.oppose || 0) + (tally.neutral || 0) + (tally.abstain || 0)
  return total > 0 ? Math.round(((tally[key] || 0) / total) * 100) : 0
}

function totalVotes(tally) {
  return (tally.agree || 0) + (tally.oppose || 0) + (tally.neutral || 0) + (tally.abstain || 0)
}
</script>

<style scoped>
.agenda-panel {
  padding: var(--space-4);
  background: var(--surface);
  border-radius: var(--radius);
  border: 1px solid var(--border);
}

.agenda-header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
  padding-bottom: var(--space-3);
  border-bottom: 1px solid var(--border);
}

.agenda-icon {
  font-size: 24px;
  flex-shrink: 0;
}

.panel-title {
  font-family: var(--font-display, inherit);
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
  margin: 0;
  letter-spacing: 0;
  text-transform: none;
}

.agenda-subtitle {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
}

.agenda-items {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.agenda-item {
  padding: var(--space-3);
  background: var(--surface-alt, rgba(255,255,255,0.02));
  border-radius: var(--radius-sm, 8px);
  border: 1px solid var(--border);
  transition: border-color var(--transition-fast, 150ms ease);
}

.agenda-item:hover {
  border-color: var(--border-hover, var(--accent));
}

.item-header {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}

.item-number {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--accent);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}

.item-content {
  flex: 1;
  min-width: 0;
}

.item-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  line-height: 1.4;
}

.item-description {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 4px;
  line-height: 1.5;
}

.vote-bar-wrap {
  box-shadow: var(--shadow-xs);
  border-radius: var(--radius-full);
  overflow: hidden;
  margin-bottom: var(--space-2);
}

.vote-bar {
  display: flex;
  height: 8px;
  background: var(--surface-alt);
}

.bar-segment {
  transition: width 0.4s ease;
}

.bar-segment.agree   { background: var(--success); }
.bar-segment.oppose  { background: var(--danger); }
.bar-segment.neutral { background: var(--text-muted); }

.vote-counts {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: 11px;
}

.pill {
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-weight: 600;
}

.pill.agree   { color: var(--success); background: rgba(39,174,96,0.12); }
.pill.oppose  { color: var(--danger);  background: rgba(192,57,43,0.12); }
.pill.neutral { color: var(--text-muted); background: var(--surface-alt); }

.vote-total {
  margin-left: auto;
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 500;
}
</style>
