<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useProvidersStore } from '../../stores/providers'

const { t } = useI18n()
const providersStore = useProvidersStore()

const props = defineProps({
  llmProvider: { type: String, default: '' },
  llmModel: { type: String, default: '' },
  llmModelDisplay: { type: String, default: '' },
})

const emit = defineEmits(['update:llmProvider', 'update:llmModel', 'update:llmModelDisplay'])

const useCustomModel = ref(false)
const customModelText = ref('')

onMounted(async () => {
  await providersStore.fetchPresets()
  // If provider/model are already set, expand the section
  if (props.llmProvider && props.llmModel) {
    useCustomModel.value = true
  }
})

// Sync the toggle with existing values
watch(() => props.llmProvider, (val) => {
  if (val && props.llmModel) useCustomModel.value = true
})

const availableProviders = computed(() => providersStore.availableProviders)

const availableModels = computed(() => {
  if (!props.llmProvider) return []
  return providersStore.getModelsForProvider(props.llmProvider)
})

function onProviderChange(e) {
  const providerId = e.target.value
  emit('update:llmProvider', providerId || null)
  // Reset model when provider changes
  emit('update:llmModel', null)
  emit('update:llmModelDisplay', null)
  customModelText.value = ''
}

function onModelChange(e) {
  const modelId = e.target.value
  emit('update:llmModel', modelId || null)
  // Set display name from the model list
  const modelEntry = availableModels.value.find(m => m.model_id === modelId)
  emit('update:llmModelDisplay', modelEntry ? modelEntry.display_name : modelId)
  customModelText.value = ''
}

function onCustomModelInput(e) {
  const val = e.target.value.trim()
  customModelText.value = val
  emit('update:llmModel', val || null)
  emit('update:llmModelDisplay', val || null)
}

function onToggle() {
  if (!useCustomModel.value) {
    // Turning off — clear the override
    emit('update:llmProvider', null)
    emit('update:llmModel', null)
    emit('update:llmModelDisplay', null)
    customModelText.value = ''
  }
}

// Determine if the current model is in the suggestions list (for showing custom input)
const isCustomModelId = computed(() => {
  if (!props.llmModel) return false
  return !availableModels.value.some(m => m.model_id === props.llmModel)
})
</script>

<template>
  <div class="llm-override-section" style="margin-top: 12px;">
    <label
      class="form-label"
      style="display: flex; align-items: center; gap: 10px; cursor: pointer; text-transform: none; font-size: 13px; font-weight: 600;"
    >
      <input
        type="checkbox"
        v-model="useCustomModel"
        @change="onToggle"
        style="width: auto;"
      />
      {{ t('stakeholders.llmOverride.toggle') }}
    </label>

    <div v-if="useCustomModel" style="padding: 12px; border: 1px solid var(--border); border-radius: var(--radius); margin-top: 8px;">
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
        <!-- Provider dropdown -->
        <div class="form-group">
          <label class="form-label">{{ t('stakeholders.llmOverride.provider') }}</label>
          <select class="form-select" :value="llmProvider || ''" @change="onProviderChange">
            <option value="">{{ t('stakeholders.llmOverride.selectProvider') }}</option>
            <option v-for="p in availableProviders" :key="p.id" :value="p.id">
              {{ p.icon }} {{ p.label }}
            </option>
          </select>
        </div>

        <!-- Model dropdown -->
        <div class="form-group">
          <label class="form-label">{{ t('stakeholders.llmOverride.model') }}</label>
          <select
            class="form-select"
            :value="llmModel || ''"
            :disabled="!llmProvider"
            @change="onModelChange"
          >
            <option value="">{{ t('stakeholders.llmOverride.selectModel') }}</option>
            <option v-for="m in availableModels" :key="m.model_id" :value="m.model_id">
              {{ m.display_name }}
            </option>
            <option value="__custom__">{{ t('stakeholders.llmOverride.customModel') }}</option>
          </select>
        </div>
      </div>

      <!-- Custom model text input (shown when "Custom..." is selected or model not in list) -->
      <div v-if="llmModel === '__custom__' || isCustomModelId" class="form-group" style="margin-top: 8px;">
        <label class="form-label">{{ t('stakeholders.llmOverride.customModelId') }}</label>
        <input
          class="form-input"
          :value="isCustomModelId ? llmModel : customModelText"
          @input="onCustomModelInput"
          placeholder="e.g. gpt-4o-2024-08-06"
        />
      </div>

      <p style="margin-top: 8px; font-size: 12px; color: var(--text-muted); line-height: 1.5;">
        {{ t('stakeholders.llmOverride.helpText') }}
      </p>
    </div>
  </div>
</template>
