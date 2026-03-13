<script setup>
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import ApiKeyInput from './ApiKeyInput.vue'
import ModelList from './ModelList.vue'

const { t } = useI18n({ useScope: 'global' })

const props = defineProps({
  preset: { type: Object, required: true },
  providerKey: { type: Object, default: null },
  models: { type: Array, default: () => [] },
  modelsLoading: { type: Boolean, default: false },
})

const emit = defineEmits(['save', 'remove', 'test', 'toggle-model', 'set-default', 'refresh-models'])

const apiKey = ref('')
const baseUrl = ref('')
const testing = ref(false)
const testResult = ref(null)
const showBaseUrl = ref(false)
const confirmRemove = ref(false)

// Reset form when provider changes
watch(() => props.preset?.id, () => {
  apiKey.value = ''
  baseUrl.value = props.providerKey?.base_url || props.preset?.base_url || ''
  testing.value = false
  testResult.value = null
  showBaseUrl.value = false
  confirmRemove.value = false
}, { immediate: true })

// Sync base_url from provider key if it exists
watch(() => props.providerKey, (key) => {
  if (key?.base_url) {
    baseUrl.value = key.base_url
  }
}, { immediate: true })

const hasExistingKey = computed(() => !!props.providerKey)

async function handleSave() {
  emit('save', {
    provider_id: props.preset.id,
    api_key: apiKey.value,
    base_url: baseUrl.value || undefined,
  })
  apiKey.value = ''
}

async function handleTest() {
  testing.value = true
  testResult.value = null
  try {
    await new Promise((resolve, reject) => {
      const handler = (result) => {
        resolve(result)
      }
      emit('test', props.preset.id, handler, (err) => reject(err))
      // If parent doesn't call back within 30s, assume success after emit
      setTimeout(() => resolve({ ok: true }), 100)
    })
  } catch {
    // error handled by parent
  } finally {
    testing.value = false
  }
}

function handleRemove() {
  if (!confirmRemove.value) {
    confirmRemove.value = true
    return
  }
  emit('remove', props.preset.id)
  confirmRemove.value = false
}
</script>

<template>
  <div class="provider-detail">
    <div class="detail-header">
      <div class="detail-title">{{ preset.label || preset.name || preset.id }}</div>
      <div v-if="preset.notes" class="detail-notes">{{ preset.notes }}</div>
    </div>

    <div class="detail-form">
      <!-- API Key -->
      <div class="form-group">
        <label class="form-label">
          {{ t('settings.providers.addKey') }}
          <span v-if="hasExistingKey" class="key-hint">({{ t('settings.apiKeyHint') }})</span>
        </label>
        <ApiKeyInput
          v-model="apiKey"
          :placeholder="preset.auth_hint || preset.api_key_placeholder || 'API key...'"
          :verified="providerKey?.verified === true"
          :testing="testing"
          @test="emit('test', preset.id)"
        />
      </div>

      <!-- Base URL override -->
      <div class="form-group">
        <button
          v-if="!showBaseUrl && !baseUrl"
          type="button"
          class="btn-link"
          @click="showBaseUrl = true"
        >
          {{ t('settings.providers.baseUrlOverride') }}
        </button>
        <template v-if="showBaseUrl || baseUrl">
          <label class="form-label">{{ t('settings.providers.baseUrlOverride') }}</label>
          <input
            class="form-input"
            v-model="baseUrl"
            :placeholder="preset.base_url || 'https://api.example.com/v1'"
          />
        </template>
      </div>

      <!-- Action buttons -->
      <div class="detail-actions">
        <button
          type="button"
          class="btn btn-primary"
          :disabled="!apiKey"
          @click="handleSave"
        >
          {{ hasExistingKey ? t('common.save') : t('settings.providers.addKey') }}
        </button>

        <button
          v-if="hasExistingKey"
          type="button"
          :class="['btn', confirmRemove ? 'btn-danger' : 'btn-ghost']"
          @click="handleRemove"
        >
          {{ confirmRemove
            ? t('settings.providers.removeConfirm', { provider: preset.label || preset.id })
            : t('settings.providers.removeKey')
          }}
        </button>
      </div>

      <!-- Model list (only for configured providers) -->
      <ModelList
        v-if="hasExistingKey"
        :models="models"
        :loading="modelsLoading"
        @toggle="(m) => emit('toggle-model', m)"
        @set-default="(m) => emit('set-default', m)"
        @refresh="emit('refresh-models')"
      />
    </div>
  </div>
</template>

<style scoped>
.provider-detail {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm, 8px);
  padding: var(--space-6, 24px);
  margin-top: var(--space-4, 16px);
}

.detail-header {
  margin-bottom: var(--space-4, 16px);
}

.detail-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text);
  font-family: var(--font-display, var(--font-sans));
}

.detail-notes {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 4px;
  line-height: 1.5;
}

.detail-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-4, 16px);
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.form-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.key-hint {
  font-weight: 400;
  text-transform: none;
  letter-spacing: normal;
}

.btn-link {
  background: none;
  border: none;
  color: var(--accent);
  font-size: 12px;
  cursor: pointer;
  padding: 0;
  text-align: left;
  text-decoration: underline;
  opacity: 0.8;
  transition: opacity var(--transition-fast);
}

.btn-link:hover {
  opacity: 1;
}

.detail-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.btn-danger {
  background: var(--danger);
  color: #fff;
  border: none;
  padding: 6px 14px;
  border-radius: var(--radius-xs, 4px);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
}

.btn-danger:hover {
  opacity: 0.9;
}
</style>
