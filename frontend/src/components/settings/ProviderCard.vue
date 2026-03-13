<script setup>
import { useI18n } from 'vue-i18n'
import ProviderIcon from './ProviderIcon.vue'

const { t } = useI18n({ useScope: 'global' })

defineProps({
  preset: { type: Object, required: true },
  configured: { type: Boolean, default: false },
  verified: { type: Boolean, default: false },
  enabled: { type: Boolean, default: false },
  selected: { type: Boolean, default: false },
})

const emit = defineEmits(['select'])
</script>

<template>
  <button
    :class="['pcard', { 'pcard--selected': selected, 'pcard--configured': configured }]"
    @click="emit('select')"
    :title="preset.notes || preset.label"
  >
    <div class="pcard-icon">
      <ProviderIcon :provider="preset.id" size="28px" />
    </div>
    <span class="pcard-label">{{ preset.label || preset.name || preset.id }}</span>
    <span v-if="verified" class="pcard-badge pcard-badge--verified">
      {{ t('settings.providers.verified') }}
    </span>
    <span v-else-if="configured" class="pcard-badge pcard-badge--configured">
      {{ t('settings.providers.configured') }}
    </span>
    <span v-else class="pcard-badge pcard-badge--none">
      {{ t('settings.providers.notConfigured') }}
    </span>
  </button>
</template>

<style scoped>
.pcard {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 16px 10px 12px;
  background: var(--surface);
  border: 1.5px solid var(--border);
  border-radius: var(--radius-sm, 8px);
  cursor: pointer;
  transition: border-color var(--transition-fast), background var(--transition-fast), box-shadow var(--transition-fast), transform var(--transition-fast);
  text-align: center;
  min-width: 0;
}

.pcard:hover {
  border-color: var(--border-hover);
  background: var(--surface-hover);
  transform: translateY(-1px);
  box-shadow: var(--shadow-sm);
}

.pcard--selected {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 8%, var(--surface));
  box-shadow: 0 0 0 1px var(--accent), var(--shadow-sm);
}

.pcard--configured {
  border-color: color-mix(in srgb, var(--provider-verified) 40%, var(--border));
}

.pcard-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
}

.pcard-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}

.pcard-badge {
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 2px 6px;
  border-radius: var(--radius-xs, 4px);
  line-height: 1.4;
  white-space: nowrap;
}

.pcard-badge--verified {
  color: var(--provider-verified);
  background: color-mix(in srgb, var(--provider-verified) 15%, transparent);
}

.pcard-badge--configured {
  color: var(--provider-unverified);
  background: color-mix(in srgb, var(--provider-unverified) 15%, transparent);
}

.pcard-badge--none {
  color: var(--provider-disabled);
  background: color-mix(in srgb, var(--provider-disabled) 10%, transparent);
}
</style>
