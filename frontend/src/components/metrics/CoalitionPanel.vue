<script setup>
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
defineProps({ coalitions: { type: Array, default: () => [] } })
</script>

<template>
  <div v-if="coalitions.length" class="panel-box">
    <div class="panel-title">{{ t('coalitionPanel.title') }}</div>
    <div
      v-for="(group, i) in coalitions"
      :key="i"
      class="cp-group"
      :style="{ borderLeftColor: group.color || 'var(--accent)' }"
    >
      <div class="cp-label" :style="{ color: group.color || 'var(--accent)' }">
        {{ group.label }}
      </div>
      <div class="cp-members">
        <span
          v-for="member in group.members"
          :key="member"
          class="cp-chip"
          :style="{ borderColor: group.color || 'var(--accent)' }"
        >{{ member }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cp-group {
  background: var(--surface-alt);
  padding: var(--space-3);
  border-radius: var(--radius-sm);
  margin-bottom: var(--space-2);
  border-left: 3px solid var(--accent);
}

.cp-group:last-child {
  margin-bottom: 0;
}

.cp-label {
  font-size: 12px;
  font-weight: 600;
  margin-bottom: var(--space-2);
}

.cp-members {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}

.cp-chip {
  font-size: 11px;
  color: var(--text-muted);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-full);
  padding: 2px 8px;
  display: inline-flex;
  align-items: center;
}
</style>
