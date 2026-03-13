import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  getProviderCatalog,
  getProviderKeys,
  saveProviderKey as apiSaveKey,
  removeProviderKey as apiRemoveKey,
  testProviderConnection as apiTestConnection,
  getModelRegistry as apiGetModelRegistry,
  refreshModels as apiRefreshModels,
  toggleModel as apiToggleModel,
  setDefaultModel as apiSetDefault,
} from '../api/client'

export const useProvidersStore = defineStore('providers', () => {
  // State
  const presets = ref([])
  const configuredKeys = ref([])
  const modelRegistry = ref([])
  const loading = ref(false)
  const error = ref(null)

  // Getters
  const enabledProviders = computed(() => {
    const keyMap = new Map(configuredKeys.value.map(k => [k.provider_id, k]))
    return presets.value.filter(p => {
      const key = keyMap.get(p.id)
      return key && key.is_enabled !== false
    })
  })

  const configuredProviderIds = computed(() =>
    configuredKeys.value.map(k => k.provider_id)
  )

  const defaultModel = computed(() =>
    modelRegistry.value.find(m => m.is_default) || null
  )

  /** Provider presets that have a base_url (i.e. actually usable). */
  const availableProviders = computed(() =>
    presets.value.filter(p => p.base_url || p.id === 'ollama' || p.id === 'lmstudio')
  )

  function modelsForProvider(providerId) {
    return modelRegistry.value.filter(m => m.provider_id === providerId)
  }

  function isConfigured(providerId) {
    return configuredKeys.value.some(k => k.provider_id === providerId)
  }

  function isVerified(providerId) {
    const key = configuredKeys.value.find(k => k.provider_id === providerId)
    return key?.verified === true
  }

  function getKeyConfig(providerId) {
    return configuredKeys.value.find(k => k.provider_id === providerId) || null
  }

  function getPresetById(id) {
    return presets.value.find(p => p.id === id) || null
  }

  /**
   * Return a list of suggested models for a given provider id.
   * Uses the model registry if available, otherwise falls back to static suggestions.
   */
  function getModelsForProvider(providerId) {
    // First try the dynamic model registry
    const registryModels = modelRegistry.value.filter(m => m.provider_id === providerId)
    if (registryModels.length > 0) return registryModels

    // Fallback to static suggestions for the LlmOverrideSection component
    const preset = getPresetById(providerId)
    if (!preset) return []

    const MODEL_SUGGESTIONS = {
      openai: [
        { model_id: 'gpt-4o', display_name: 'GPT-4o' },
        { model_id: 'gpt-4o-mini', display_name: 'GPT-4o Mini' },
        { model_id: 'o1', display_name: 'o1' },
        { model_id: 'o3-mini', display_name: 'o3-mini' },
      ],
      anthropic: [
        { model_id: 'claude-opus-4-5', display_name: 'Claude Opus 4.5' },
        { model_id: 'claude-sonnet-4', display_name: 'Claude Sonnet 4' },
        { model_id: 'claude-3-5-haiku-latest', display_name: 'Claude 3.5 Haiku' },
      ],
      deepseek: [
        { model_id: 'deepseek-chat', display_name: 'DeepSeek Chat (V3)' },
        { model_id: 'deepseek-reasoner', display_name: 'DeepSeek Reasoner (R1)' },
      ],
      groq: [
        { model_id: 'llama-3.3-70b-versatile', display_name: 'Llama 3.3 70B' },
        { model_id: 'mixtral-8x7b-32768', display_name: 'Mixtral 8x7B' },
      ],
      openrouter: [
        { model_id: 'meta-llama/llama-3.3-70b-instruct', display_name: 'Llama 3.3 70B' },
        { model_id: 'openai/gpt-4o', display_name: 'GPT-4o' },
        { model_id: 'anthropic/claude-opus-4-5', display_name: 'Claude Opus 4.5' },
      ],
      mistral: [
        { model_id: 'mistral-large-latest', display_name: 'Mistral Large' },
        { model_id: 'codestral-latest', display_name: 'Codestral' },
      ],
    }

    return MODEL_SUGGESTIONS[providerId] || [
      { model_id: preset.placeholder_model, display_name: preset.placeholder_model },
    ]
  }

  // Actions
  async function fetchPresets() {
    try {
      const res = await getProviderCatalog()
      presets.value = res.data?.providers || res.data || []
    } catch (e) {
      presets.value = []
      error.value = e.message
    }
  }

  async function fetchKeys() {
    try {
      const res = await getProviderKeys()
      configuredKeys.value = res.data?.keys || res.data || []
    } catch (e) {
      configuredKeys.value = []
      error.value = e.message
    }
  }

  async function fetchModelRegistry() {
    try {
      const res = await apiGetModelRegistry()
      modelRegistry.value = res.data?.models || res.data || []
    } catch (e) {
      modelRegistry.value = []
      error.value = e.message
    }
  }

  async function saveKey(providerId, apiKey, baseUrl) {
    loading.value = true
    error.value = null
    try {
      const payload = { provider_id: providerId, api_key: apiKey }
      if (baseUrl) payload.base_url = baseUrl
      await apiSaveKey(payload)
      await fetchKeys()
    } catch (e) {
      error.value = e.response?.data?.detail || e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  async function removeKey(providerId) {
    loading.value = true
    error.value = null
    try {
      await apiRemoveKey(providerId)
      await fetchKeys()
    } catch (e) {
      error.value = e.response?.data?.detail || e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  async function testConnection(providerId) {
    error.value = null
    try {
      const res = await apiTestConnection(providerId)
      // Refresh keys to pick up verified status
      await fetchKeys()
      return res.data
    } catch (e) {
      error.value = e.response?.data?.detail || e.message
      throw e
    }
  }

  async function doRefreshModels() {
    loading.value = true
    error.value = null
    try {
      await apiRefreshModels()
      await fetchModelRegistry()
    } catch (e) {
      error.value = e.response?.data?.detail || e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  async function doToggleModel(providerId, modelId) {
    error.value = null
    try {
      await apiToggleModel(providerId, modelId)
      await fetchModelRegistry()
    } catch (e) {
      error.value = e.response?.data?.detail || e.message
      throw e
    }
  }

  async function doSetDefault(providerId, modelId) {
    error.value = null
    try {
      await apiSetDefault({ provider_id: providerId, model_id: modelId })
      await fetchModelRegistry()
    } catch (e) {
      error.value = e.response?.data?.detail || e.message
      throw e
    }
  }

  return {
    // State
    presets,
    configuredKeys,
    modelRegistry,
    loading,
    error,
    // Getters
    enabledProviders,
    configuredProviderIds,
    defaultModel,
    availableProviders,
    // Methods
    modelsForProvider,
    isConfigured,
    isVerified,
    getKeyConfig,
    getPresetById,
    getModelsForProvider,
    // Actions
    fetchPresets,
    fetchKeys,
    fetchModelRegistry,
    saveKey,
    removeKey,
    testConnection,
    refreshModels: doRefreshModels,
    toggleModel: doToggleModel,
    setDefault: doSetDefault,
  }
})
