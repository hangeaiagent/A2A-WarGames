<script setup>
import { useI18n } from 'vue-i18n'
import ModelCard from './ModelCard.vue'
import Spinner from '../common/Spinner.vue'

const { t } = useI18n({ useScope: 'global' })

defineProps({
  models: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})

const emit = defineEmits(['toggle', 'set-default', 'refresh'])
</script>

<template>
  <div class="model-list">
    <div class="model-list-header">
      <span class="model-list-title">{{ t('settings.providers.models') }}</span>
      <button
        type="button"
        class="btn btn-ghost refresh-btn"
        :disabled="loading"
        @click="emit('refresh')"
      >
        <Spinner v-if="loading" size="14px" />
        <span v-else>{{ t('settings.providers.refreshModels') }}</span>
      </button>
    </div>

    <div v-if="loading && !models.length" class="model-list-loading">
      <Spinner size="20px" />
    </div>

    <div v-else-if="!models.length" class="model-list-empty">
      {{ t('settings.providers.noModels') }}
    </div>

    <div v-else class="model-list-items">
      <ModelCard
        v-for="m in models"
        :key="m.model_id"
        :model="m"
        @toggle="emit('toggle', m)"
        @set-default="emit('set-default', m)"
      />
    </div>
  </div>
</template>

<style scoped>
.model-list {
  margin-top: var(--space-4, 16px);
}

.model-list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-2, 8px);
}

.model-list-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}

.refresh-btn {
  font-size: 12px;
  padding: 4px 10px;
}

.model-list-items {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm, 8px);
  background: var(--bg);
  overflow: hidden;
}

.model-list-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-6, 24px);
}

.model-list-empty {
  font-size: 12px;
  color: var(--text-muted);
  text-align: center;
  padding: var(--space-6, 24px);
  border: 1px dashed var(--border);
  border-radius: var(--radius-sm, 8px);
}
</style>
