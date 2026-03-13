<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import ProviderIcon from './ProviderIcon.vue'

const { t } = useI18n({ useScope: 'global' })

const props = defineProps({
  defaultModel: { type: Object, default: null },
  presets: { type: Array, default: () => [] },
})

const providerPreset = computed(() => {
  if (!props.defaultModel) return null
  return props.presets.find(p => p.id === props.defaultModel.provider_id) || null
})
</script>

<template>
  <div class="default-model-selector">
    <div class="selector-label">{{ t('settings.providers.default') }}</div>
    <div v-if="defaultModel && providerPreset" class="selector-current">
      <ProviderIcon :provider="providerPreset.id" size="18px" />
      <span class="selector-provider">{{ providerPreset.label || providerPreset.name }}</span>
      <span class="selector-separator">/</span>
      <span class="selector-model">{{ defaultModel.display_name || defaultModel.model_id }}</span>
    </div>
    <div v-else class="selector-empty">
      {{ t('settings.providers.noDefault') }}
    </div>
  </div>
</template>

<style scoped>
.default-model-selector {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm, 8px);
  padding: var(--space-4, 16px);
  margin-top: var(--space-4, 16px);
}

.selector-label {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  margin-bottom: var(--space-2, 8px);
}

.selector-current {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

.selector-provider {
  font-weight: 600;
  color: var(--text);
}

.selector-separator {
  color: var(--text-muted);
  opacity: 0.5;
}

.selector-model {
  color: var(--text);
  font-family: var(--font-mono);
  font-size: 13px;
}

.selector-empty {
  font-size: 13px;
  color: var(--text-muted);
  font-style: italic;
}
</style>
