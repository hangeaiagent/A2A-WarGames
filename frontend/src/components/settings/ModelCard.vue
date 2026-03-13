<script setup>
import { useI18n } from 'vue-i18n'

const { t } = useI18n({ useScope: 'global' })

defineProps({
  model: { type: Object, required: true },
})

const emit = defineEmits(['toggle', 'set-default'])

const tierColors = {
  fast: 'var(--tier-fast)',
  balanced: 'var(--tier-balanced)',
  quality: 'var(--tier-quality)',
  reasoning: 'var(--tier-reasoning)',
}

function formatContextWindow(val) {
  if (!val) return ''
  if (val >= 1000000) return `${(val / 1000000).toFixed(1)}M`
  if (val >= 1000) return `${Math.round(val / 1000)}k`
  return String(val)
}
</script>

<template>
  <div :class="['model-card', { 'model-card--inactive': !model.is_active }]">
    <div class="model-main">
      <div class="model-info">
        <span class="model-name">{{ model.display_name || model.model_id }}</span>
        <span
          v-if="model.tier"
          class="tier-badge"
          :style="{ '--tier-color': tierColors[model.tier] || 'var(--text-muted)' }"
        >
          {{ t('settings.providers.modelTiers.' + model.tier, model.tier) }}
        </span>
        <span v-if="model.context_window" class="context-window">
          {{ formatContextWindow(model.context_window) }} ctx
        </span>
      </div>
      <div class="model-capabilities">
        <span v-if="model.supports_vision" class="capability" :title="t('settings.providers.capabilities.vision')">&#x1F441;</span>
        <span v-if="model.supports_thinking" class="capability" :title="t('settings.providers.capabilities.thinking')">&#x1F9E0;</span>
        <span v-if="model.supports_streaming" class="capability" :title="t('settings.providers.capabilities.streaming')">&#x26A1;</span>
        <span v-if="model.supports_json" class="capability" :title="t('settings.providers.capabilities.json')">{}</span>
      </div>
    </div>
    <div class="model-actions">
      <label class="default-radio" :title="t('settings.providers.setDefault')">
        <input
          type="radio"
          name="default-model"
          :checked="model.is_default"
          @change="emit('set-default')"
        />
        <span class="radio-label">{{ t('settings.providers.default') }}</span>
      </label>
      <button
        type="button"
        role="switch"
        :aria-checked="model.is_active ? 'true' : 'false'"
        :aria-label="model.display_name || model.model_id"
        class="model-toggle"
        :class="{ on: model.is_active }"
        @click="emit('toggle')"
      >
        <div class="model-toggle-knob"></div>
      </button>
    </div>
  </div>
</template>

<style scoped>
.model-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3, 12px);
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  transition: opacity var(--transition-fast);
}

.model-card:last-child {
  border-bottom: none;
}

.model-card--inactive {
  opacity: 0.5;
}

.model-main {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  flex: 1;
}

.model-info {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.model-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tier-badge {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--tier-color);
  background: color-mix(in srgb, var(--tier-color) 15%, transparent);
  padding: 1px 6px;
  border-radius: var(--radius-xs, 4px);
  line-height: 1.5;
}

.context-window {
  font-size: 11px;
  color: var(--text-muted);
  font-family: var(--font-mono);
}

.model-capabilities {
  display: flex;
  gap: 6px;
}

.capability {
  font-size: 12px;
  opacity: 0.7;
  cursor: default;
}

.model-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.default-radio {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  font-size: 11px;
  color: var(--text-muted);
}

.default-radio input[type="radio"] {
  accent-color: var(--accent);
  cursor: pointer;
}

.radio-label {
  white-space: nowrap;
}

.model-toggle {
  width: 36px;
  height: 20px;
  border-radius: 10px;
  background: var(--border);
  position: relative;
  cursor: pointer;
  transition: background var(--transition-base);
  flex-shrink: 0;
  border: none;
  padding: 0;
  outline-offset: 2px;
}

.model-toggle.on {
  background: var(--accent);
}

.model-toggle-knob {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #fff;
  position: absolute;
  top: 2px;
  left: 2px;
  transition: transform var(--transition-base);
}

.model-toggle.on .model-toggle-knob {
  transform: translateX(16px);
}

@media (max-width: 640px) {
  .model-card {
    flex-direction: column;
    align-items: flex-start;
  }

  .model-actions {
    width: 100%;
    justify-content: space-between;
    margin-top: 4px;
  }
}
</style>
