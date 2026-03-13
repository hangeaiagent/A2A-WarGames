<script setup>
import { useI18n } from 'vue-i18n'
import ProviderIcon from './ProviderIcon.vue'

const { t } = useI18n()

defineProps({
  modelValue: { type: String, default: '' },
  providers: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue'])

function select(id) {
  emit('update:modelValue', id)
}

// Providers that get a "recommended" badge
const recommended = new Set(['openai', 'google', 'groq'])
</script>

<template>
  <div class="provider-selector">
    <div class="provider-grid">
      <button
        v-for="p in providers"
        :key="p.id"
        :class="['provider-card', { selected: modelValue === p.id }]"
        @click="select(p.id)"
        :title="p.notes"
      >
        <ProviderIcon :provider="p.id" size="22px" />
        <span class="provider-name">{{ p.name }}</span>
        <span v-if="recommended.has(p.id)" class="provider-badge">{{ t('settings.recommended') || 'Recommended' }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.provider-selector {
  margin-bottom: 20px;
}

.provider-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.provider-card {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: var(--surface);
  border: 1.5px solid var(--border);
  border-radius: var(--radius-sm, 8px);
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  color: var(--text);
  transition: all var(--transition-fast, 150ms ease);
  position: relative;
  white-space: nowrap;
}

.provider-card:hover {
  border-color: var(--border-hover, var(--accent));
  background: var(--surface-hover, rgba(255,255,255,0.04));
  transform: translateY(-1px);
  box-shadow: var(--shadow-sm, 0 2px 8px rgba(0,0,0,0.15));
}

.provider-card.selected {
  border-color: var(--accent);
  background: var(--accent-glow);
  box-shadow: 0 0 0 1px var(--accent), 0 2px 12px color-mix(in srgb, var(--accent) 15%, transparent);
}

.provider-card.selected .provider-name {
  color: var(--accent);
  font-weight: 600;
}

.provider-name {
  font-family: var(--font-sans, inherit);
}

.provider-badge {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 12%, transparent);
  padding: 2px 5px;
  border-radius: 3px;
  line-height: 1;
}
</style>
