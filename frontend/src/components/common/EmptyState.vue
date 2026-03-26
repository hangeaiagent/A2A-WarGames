<script setup>
import { useI18n } from 'vue-i18n'
const { t } = useI18n()

defineProps({
  icon: { type: String, default: '📭' },
  title: { type: String, default: '' },
  subtitle: { type: String, default: '' },
})
</script>

<template>
  <div class="empty-state-card">
    <div class="empty-icon">{{ icon }}</div>
    <div class="empty-title">{{ title || t('common.nothingHereYet') }}</div>
    <div v-if="subtitle" class="empty-subtitle">{{ subtitle }}</div>
    <slot />
  </div>
</template>

<style scoped>
.empty-state-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-10) var(--space-6);
  text-align: center;
  animation: fade-in 300ms ease;
}
.empty-icon {
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  background: var(--surface-hover);
  border-radius: var(--radius-full);
  margin-bottom: var(--space-4);
}
.empty-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: var(--space-1);
}
.empty-subtitle {
  font-size: 12px;
  color: var(--text-muted);
  max-width: 260px;
  line-height: 1.5;
}
</style>
