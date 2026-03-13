<script setup>
import ProviderCard from './ProviderCard.vue'

defineProps({
  presets: { type: Array, default: () => [] },
  configuredKeys: { type: Array, default: () => [] },
  selectedId: { type: String, default: null },
})

const emit = defineEmits(['select'])

function isConfigured(providerId, keys) {
  return keys.some(k => k.provider_id === providerId)
}

function isVerified(providerId, keys) {
  const key = keys.find(k => k.provider_id === providerId)
  return key?.verified === true
}

function isEnabled(providerId, keys) {
  const key = keys.find(k => k.provider_id === providerId)
  return key?.is_enabled !== false && isConfigured(providerId, keys)
}
</script>

<template>
  <div class="provider-grid">
    <ProviderCard
      v-for="preset in presets"
      :key="preset.id"
      :preset="preset"
      :configured="isConfigured(preset.id, configuredKeys)"
      :verified="isVerified(preset.id, configuredKeys)"
      :enabled="isEnabled(preset.id, configuredKeys)"
      :selected="selectedId === preset.id"
      @select="emit('select', preset.id)"
    />
  </div>
</template>

<style scoped>
.provider-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}

@media (max-width: 768px) {
  .provider-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 480px) {
  .provider-grid {
    grid-template-columns: 1fr;
  }
}
</style>
