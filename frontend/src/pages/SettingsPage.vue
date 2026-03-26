<script setup>
import { ref, inject, onMounted, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useSettingsStore } from '../stores/settings'
import { useProvidersStore } from '../stores/providers'
import { useTheme } from '../composables/useTheme'
import ProviderGrid from '../components/settings/ProviderGrid.vue'
import ProviderDetail from '../components/settings/ProviderDetail.vue'
import DefaultModelSelector from '../components/settings/DefaultModelSelector.vue'
import api, { getAvailableVoices } from '../api/client'

const { t, locale } = useI18n({ useScope: 'global' })
const { theme: currentTheme, setTheme: setCurrentTheme } = useTheme()
const route = useRoute()
const router = useRouter()

const auth = useAuthStore()
const showLogin = inject('showLogin')
const store = useSettingsStore()
const providersStore = useProvidersStore()
const loading = ref(false)
const saved = ref(false)
const form = ref(null)
const activeTab = ref('llm')
const availableModels = ref([])
const modelsLoading = ref(false)
const availableVoices = ref(["alloy", "echo", "fable", "onyx", "nova", "shimmer"])
const selectedProviderId = ref(null)

const defaultFlags = {
  thinking_bubbles: true,
  mention_routing: false,
  thinking_indicator: true,
  notification_sounds: false,
  cross_session_memory: false,
  context_meter: true,
  compact_conversation: true,
  sbert_meter: false,
  ai_assistant: false,
  agent_memory: false,
  private_threads: false,
  streaming_tokens: true,
  concordia_engine: false,
  dag_visualization: true,
}

const flagLabels = [
  { key: 'thinking_bubbles' },
  { key: 'mention_routing' },
  { key: 'thinking_indicator' },
  { key: 'notification_sounds' },
  { key: 'cross_session_memory' },
  { key: 'context_meter' },
  { key: 'compact_conversation' },
  { key: 'sbert_meter' },
  { key: 'ai_assistant' },
  { key: 'agent_memory' },
  { key: 'private_threads' },
  { key: 'streaming_tokens' },
  { key: 'concordia_engine' },
  { key: 'dag_visualization' },
]

const featureFlags = ref({ ...defaultFlags })
const allowedTabs = ['llm', 'voice', 'features', 'appearance']

function selectTab(tab, syncQuery = true) {
  if (!allowedTabs.includes(tab)) return
  activeTab.value = tab
  if (!syncQuery) return
  router.replace({ query: { tab } })
}

async function fetchModels() {
  modelsLoading.value = true
  try {
    const res = await api.get('/api/settings/models')
    availableModels.value = res.data?.models || []
  } catch {
    availableModels.value = []
  } finally {
    modelsLoading.value = false
  }
}

// Provider management helpers
function selectProvider(providerId) {
  selectedProviderId.value = selectedProviderId.value === providerId ? null : providerId
}

const selectedPreset = computed(() => {
  if (!selectedProviderId.value) return null
  return providersStore.presets.find(p => p.id === selectedProviderId.value) || null
})

const selectedProviderKey = computed(() => {
  if (!selectedProviderId.value) return null
  return providersStore.getKeyConfig(selectedProviderId.value)
})

const selectedProviderModels = computed(() => {
  if (!selectedProviderId.value) return []
  return providersStore.modelsForProvider(selectedProviderId.value)
})

async function handleSaveKey(data) {
  try {
    await providersStore.saveKey(data.provider_id, data.api_key, data.base_url)
    saved.value = true
    setTimeout(() => { saved.value = false }, 2500)
  } catch {
    // error shown by store
  }
}

async function handleRemoveKey(providerId) {
  try {
    await providersStore.removeKey(providerId)
  } catch {
    // error shown by store
  }
}

async function handleTestConnection(providerId) {
  try {
    await providersStore.testConnection(providerId)
  } catch {
    // error shown by store
  }
}

async function handleToggleModel(model) {
  try {
    await providersStore.toggleModel(model.provider_id, model.model_id)
  } catch {
    // error shown by store
  }
}

async function handleSetDefault(model) {
  try {
    await providersStore.setDefault(model.provider_id, model.model_id)
  } catch {
    // error shown by store
  }
}

async function handleRefreshModels() {
  try {
    await providersStore.refreshModels()
  } catch {
    // error shown by store
  }
}

function profileToForm(p) {
  return {
    ...p,
    council_models: (p.council_models || []).join(', '),
    api_key: '',
    tts_enabled: p.tts_enabled ?? false,
    tts_model: p.tts_model ?? 'tts-1',
    tts_voice: p.tts_voice ?? 'alloy',
    tts_speed: p.tts_speed ?? 1.0,
    tts_auto_play: p.tts_auto_play ?? false,
    tts_language: p.tts_language ?? 'auto',
    stt_enabled: p.stt_enabled ?? false,
    stt_model: p.stt_model ?? 'whisper-1',
    stt_language: p.stt_language ?? 'auto',
    stt_auto_send: p.stt_auto_send ?? false,
  }
}

onMounted(async () => {
  if (typeof route.query.tab === 'string') {
    selectTab(route.query.tab, false)
  }
  if (auth.isGuest) return
  await store.fetchProfiles()
  if (store.activeProfile) {
    form.value = profileToForm(store.activeProfile)
    const existingFlags = store.activeProfile.feature_flags || {}
    featureFlags.value = { ...defaultFlags, ...existingFlags }
  }
  await Promise.all([
    fetchModels(),
    providersStore.fetchPresets(),
    providersStore.fetchKeys(),
    providersStore.fetchModelRegistry(),
  ])
  try {
    const { data } = await getAvailableVoices()
    if (data?.voices?.length) availableVoices.value = data.voices
  } catch { /* keep defaults */ }
})

watch(() => route.query.tab, (tab) => {
  if (typeof tab === 'string' && tab !== activeTab.value) {
    selectTab(tab, false)
  }
})

async function save() {
  loading.value = true
  try {
    const payload = {
      ...form.value,
      council_models: form.value.council_models.split(',').map(s => s.trim()).filter(Boolean),
    }
    await store.saveProfile(payload)
    saved.value = true
    setTimeout(() => { saved.value = false }, 2500)
    await store.fetchProfiles()
  } finally {
    loading.value = false
  }
}

async function saveFeatureFlags() {
  loading.value = true
  try {
    const profileName = store.activeProfile?.profile_name
    if (!profileName) return
    const payload = {
      ...store.activeProfile,
      feature_flags: { ...featureFlags.value },
    }
    await store.saveProfile(payload)
    saved.value = true
    setTimeout(() => { saved.value = false }, 2500)
    await store.fetchProfiles()
  } finally {
    loading.value = false
  }
}

function selectProfile(p) {
  form.value = profileToForm(p)
  const existingFlags = p.feature_flags || {}
  featureFlags.value = { ...defaultFlags, ...existingFlags }
  if (!p.is_active) store.setActiveProfile(p.profile_name)
}

function changeLocale(lang) {
  locale.value = lang
  localStorage.setItem('app-locale', lang)
}

</script>

<template>
  <div style="max-width: 680px;">
    <div class="page-header">
      <div>
        <div class="page-title">{{ t('settings.title') }}</div>
        <div class="page-subtitle">{{ t('settings.subtitle') }}</div>
      </div>
    </div>

    <!-- Guest overlay -->
    <div v-if="auth.isGuest" class="settings-card" style="text-align: center; padding: 48px 24px;">
      <div style="font-size: 40px; margin-bottom: 16px;">🔒</div>
      <h3 style="margin-bottom: 8px;">{{ t('guest.signInToCustomize') }}</h3>
      <p style="color: var(--text-muted); margin-bottom: 20px; font-size: 13px;">
        {{ t('guest.settingsRequireAuth') }}
      </p>
      <button class="btn btn-primary" @click="showLogin = true">{{ t('nav.signIn') }}</button>
    </div>

    <!-- Tab bar -->
    <div v-if="!auth.isGuest" class="settings-tabs">
      <button :class="['settings-tab', { active: activeTab === 'llm' }]" @click="selectTab('llm')">
        {{ t('settings.llmSettings') }}
      </button>
      <button :class="['settings-tab', { active: activeTab === 'voice' }]" @click="selectTab('voice')">
        {{ t('settings.voice') }}
      </button>
      <button :class="['settings-tab', { active: activeTab === 'features' }]" @click="selectTab('features')">
        {{ t('settings.experimentalFeatures') }}
      </button>
      <button :class="['settings-tab', { active: activeTab === 'appearance' }]" @click="selectTab('appearance')">
        {{ t('settings.appearance') }}
      </button>
    </div>

    <!-- LLM Providers tab -->
    <div v-if="!auth.isGuest && activeTab === 'llm'">
      <div class="providers-section">
        <div class="section-header">
          <div class="section-title" style="margin-top: 0;">{{ t('settings.providers.title') }}</div>
          <p class="section-hint">{{ t('settings.providerQuickSetupHint') }}</p>
        </div>

        <!-- Provider grid -->
        <ProviderGrid
          :presets="providersStore.presets"
          :configured-keys="providersStore.configuredKeys"
          :selected-id="selectedProviderId"
          @select="selectProvider"
        />

        <!-- Provider detail panel -->
        <ProviderDetail
          v-if="selectedPreset"
          :preset="selectedPreset"
          :provider-key="selectedProviderKey"
          :models="selectedProviderModels"
          :models-loading="providersStore.loading"
          @save="handleSaveKey"
          @remove="handleRemoveKey"
          @test="handleTestConnection"
          @toggle-model="handleToggleModel"
          @set-default="handleSetDefault"
          @refresh-models="handleRefreshModels"
        />

        <!-- Error display -->
        <div v-if="providersStore.error" class="provider-error">
          {{ providersStore.error }}
        </div>

        <!-- Default model selector -->
        <DefaultModelSelector
          :default-model="providersStore.defaultModel"
          :presets="providersStore.presets"
        />

        <!-- Legacy profile settings (collapsed) -->
        <details v-if="form" class="legacy-settings">
          <summary class="legacy-settings-toggle">{{ t('settings.generation') }} &amp; {{ t('settings.profiles') }}</summary>
          <div class="settings-card" style="margin-top: 12px;">
            <div v-if="store.profiles.length > 1" style="margin-bottom: 24px;">
              <div class="section-title" style="margin-top: 0;">{{ t('settings.profiles') }}</div>
              <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                <button v-for="p in store.profiles" :key="p.id"
                  :class="['btn', p.is_active ? 'btn-primary' : 'btn-ghost']"
                  @click="selectProfile(p)">
                  {{ p.profile_name }} {{ p.is_active ? '&#x2713;' : '' }}
                </button>
              </div>
            </div>

            <div class="form-group">
              <label class="form-label" for="settings-profile-name">{{ t('settings.profileName') }}</label>
              <input id="settings-profile-name" class="form-input" v-model="form.profile_name" />
            </div>

            <div class="section-title">{{ t('settings.endpoint') }}</div>
            <div class="form-group">
              <label class="form-label" for="settings-base-url">{{ t('settings.baseUrl') }}</label>
              <input id="settings-base-url" class="form-input" v-model="form.base_url" placeholder="https://api.openai.com/v1" />
            </div>
            <div class="form-group">
              <label class="form-label" for="settings-api-key">{{ t('settings.apiKey') }} {{ store.activeProfile?.api_key === '***' ? t('settings.apiKeyHint') : '' }}</label>
              <input id="settings-api-key" class="form-input" type="password" v-model="form.api_key" placeholder="API key..." />
            </div>

            <div class="section-title">{{ t('settings.models') }}</div>
            <div class="form-group">
              <label class="form-label">{{ t('settings.defaultModel') }}</label>
              <div style="display: flex; gap: 8px; align-items: center;">
                <select v-if="availableModels.length" class="form-input" v-model="form.default_model">
                  <option v-for="m in availableModels" :key="m" :value="m">{{ m }}</option>
                </select>
                <input v-else class="form-input" v-model="form.default_model" placeholder="gpt-4o" />
                <button class="btn btn-ghost" style="flex-shrink: 0;" @click="fetchModels" :disabled="modelsLoading" title="Refresh model list" aria-label="Refresh model list">
                  {{ modelsLoading ? '...' : '&#x21BB;' }}
                </button>
              </div>
            </div>
            <div class="form-group">
              <label class="form-label">{{ t('settings.councilModels') }}</label>
              <input class="form-input" v-model="form.council_models" placeholder="gpt-4o, gpt-4o-mini, gpt-4o" />
              <div style="font-size: 11px; color: var(--text-muted); margin-top: 4px;">
                {{ t('settings.councilModelsHint') }}
              </div>
            </div>
            <div class="form-group">
              <label class="form-label">{{ t('settings.chairmanModel') }}</label>
              <select v-if="availableModels.length" class="form-input" v-model="form.chairman_model">
                <option v-for="m in availableModels" :key="m" :value="m">{{ m }}</option>
              </select>
              <input v-else class="form-input" v-model="form.chairman_model" placeholder="gpt-4o" />
            </div>

            <div class="section-title">{{ t('settings.generation') }}</div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
              <div class="form-group">
                <label class="form-label">{{ t('settings.temperature') }}</label>
                <input type="number" min="0" max="2" step="0.05" class="form-input" v-model.number="form.temperature" />
              </div>
              <div class="form-group">
                <label class="form-label">{{ t('settings.maxTokens') }}</label>
                <input type="number" min="128" max="8192" step="128" class="form-input" v-model.number="form.max_tokens" />
              </div>
            </div>

            <div style="display: flex; gap: 10px; margin-top: 8px;">
              <button class="btn btn-primary" @click="save" :disabled="loading">
                {{ loading ? t('settings.saving') : t('settings.saveSettings') }}
              </button>
              <span v-if="saved" style="color: var(--success); font-size: 13px; align-self: center;">{{ t('settings.saved') }}</span>
            </div>
          </div>
        </details>

        <div class="settings-card" style="margin-top: 24px;">
          <div class="section-title" style="margin-top: 0;">{{ t('settings.aboutEndpoint') }}</div>
          <p style="font-size: 13px; color: var(--text-muted); line-height: 1.7;">
            {{ t('settings.aboutEndpointText') }}
          </p>
        </div>
      </div>
    </div>

    <!-- Voice tab -->
    <div v-if="!auth.isGuest && activeTab === 'voice'">
      <div v-if="!form" class="empty-state"><p>{{ t('settings.loadingSettings') }}</p></div>
      <template v-else>
        <div class="settings-card">
          <div class="section-title" style="margin-top: 0;">{{ t('settings.tts') }}</div>

          <div class="form-group" style="display: flex; align-items: center; gap: 12px;">
            <label class="form-label" style="margin-bottom: 0;">{{ t('settings.ttsEnabled') }}</label>
            <input type="checkbox" v-model="form.tts_enabled" />
          </div>

          <template v-if="form.tts_enabled">
            <div class="form-group">
              <label class="form-label">{{ t('settings.ttsModel') }}</label>
              <input class="form-input" v-model="form.tts_model" placeholder="tts-1" />
            </div>
            <div class="form-group">
              <label class="form-label">{{ t('settings.ttsVoice') }}</label>
              <select class="form-input" v-model="form.tts_voice">
                <option v-for="v in availableVoices" :key="v" :value="v">{{ v }}</option>
              </select>
            </div>
            <div class="form-group">
              <label class="form-label">{{ t('settings.speed', { speed: form.tts_speed }) }}</label>
              <input type="range" v-model.number="form.tts_speed" min="0.5" max="2.0" step="0.1" style="width: 100%;" />
            </div>
            <div class="form-group" style="display: flex; align-items: center; gap: 12px;">
              <label class="form-label" style="margin-bottom: 0;">{{ t('settings.autoPlayNewTurns') }}</label>
              <input type="checkbox" v-model="form.tts_auto_play" />
            </div>
            <div class="form-group">
              <label class="form-label">{{ t('settings.ttsLanguage') }}</label>
              <select class="form-input" v-model="form.tts_language">
                <option value="auto">{{ t('settings.auto') }}</option>
                <option value="en">English</option>
                <option value="fr">Français</option>
                <option value="es">Español</option>
                <option value="zh">中文</option>
              </select>
            </div>
          </template>

          <div class="section-title">{{ t('settings.stt') }}</div>

          <div class="form-group" style="display: flex; align-items: center; gap: 12px;">
            <label class="form-label" style="margin-bottom: 0;">{{ t('settings.sttEnabled') }}</label>
            <input type="checkbox" v-model="form.stt_enabled" />
          </div>

          <template v-if="form.stt_enabled">
            <div class="form-group">
              <label class="form-label">{{ t('settings.sttModel') }}</label>
              <input class="form-input" v-model="form.stt_model" placeholder="whisper-1" />
            </div>
            <div class="form-group">
              <label class="form-label">{{ t('settings.sttLanguage') }}</label>
              <select class="form-input" v-model="form.stt_language">
                <option value="auto">{{ t('settings.autoDetect') }}</option>
                <option value="en">English</option>
                <option value="fr">Français</option>
                <option value="es">Español</option>
                <option value="zh">中文</option>
              </select>
            </div>
            <div class="form-group" style="display: flex; align-items: center; gap: 12px;">
              <label class="form-label" style="margin-bottom: 0;">{{ t('settings.autoSendAfterTranscription') }}</label>
              <input type="checkbox" v-model="form.stt_auto_send" />
            </div>
          </template>

          <div style="display: flex; gap: 10px; margin-top: 16px;">
            <button class="btn btn-primary" @click="save" :disabled="loading">
              {{ loading ? t('settings.saving') : t('settings.saveVoiceSettings') }}
            </button>
            <span v-if="saved" style="color: var(--success); font-size: 13px; align-self: center;">{{ t('settings.saved') }}</span>
          </div>
        </div>
      </template>
    </div>

    <!-- Experimental Features tab -->
    <div v-if="!auth.isGuest && activeTab === 'features'">
      <div class="settings-card">
        <div class="section-title" style="margin-top: 0;">{{ t('settings.featureFlags') }}</div>
        <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 16px;">
          {{ t('settings.featureFlagsHint') }}
        </p>

        <div v-for="flag in flagLabels" :key="flag.key" class="feature-flag-row">
          <div class="feature-flag-label">
            <div class="feature-flag-text-group">
              <span class="feature-flag-text" :id="'flag-label-' + flag.key">{{ t('featureFlags.' + flag.key) }}</span>
              <span class="feature-flag-desc">{{ t('featureFlags.' + flag.key + '_desc', '') }}</span>
            </div>
            <button
              type="button"
              role="switch"
              :aria-checked="featureFlags[flag.key] ? 'true' : 'false'"
              :aria-labelledby="'flag-label-' + flag.key"
              class="feature-toggle"
              :class="{ on: featureFlags[flag.key] }"
              @click="featureFlags[flag.key] = !featureFlags[flag.key]"
            >
              <div class="feature-toggle-knob"></div>
            </button>
          </div>
        </div>

        <div style="display: flex; gap: 10px; margin-top: 20px;">
          <button class="btn btn-primary" @click="saveFeatureFlags" :disabled="loading">
            {{ loading ? t('settings.saving') : t('settings.saveFeatureFlags') }}
          </button>
          <span v-if="saved" style="color: var(--success); font-size: 13px; align-self: center;">{{ t('settings.saved') }}</span>
        </div>
      </div>
    </div>

    <!-- Appearance tab -->
    <div v-if="!auth.isGuest && activeTab === 'appearance'">
      <div class="settings-card">
        <div class="section-title" style="margin-top: 0;">{{ t('settings.themeLabel') }}</div>
        <div style="display: flex; gap: 8px; margin-bottom: 24px;">
          <button :class="['btn', currentTheme === 'dark' ? 'btn-primary' : 'btn-ghost']" @click="setCurrentTheme('dark')">
            🌙 {{ t('theme.dark') }}
          </button>
          <button :class="['btn', currentTheme === 'light' ? 'btn-primary' : 'btn-ghost']" @click="setCurrentTheme('light')">
            ☀️ {{ t('theme.light') }}
          </button>
        </div>
        <div class="section-title">{{ t('settings.languageLabel') }}</div>
        <div style="display: flex; gap: 8px;">
          <button :class="['btn', locale === 'en' ? 'btn-primary' : 'btn-ghost']" @click="changeLocale('en')">
            {{ t('language.en') }}
          </button>
          <button :class="['btn', locale === 'fr' ? 'btn-primary' : 'btn-ghost']" @click="changeLocale('fr')">
            {{ t('language.fr') }}
          </button>
          <button :class="['btn', locale === 'es' ? 'btn-primary' : 'btn-ghost']" @click="changeLocale('es')">
            {{ t('language.es') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.settings-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 24px;
}

.settings-tabs {
  display: flex;
  gap: 0;
  margin-bottom: 24px;
  border-bottom: 1px solid var(--border);
}
.settings-tab {
  padding: 10px 20px;
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  transition: color 0.15s, border-color 0.15s;
}
.settings-tab:hover {
  color: var(--text);
}
.settings-tab.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}


/* Feature flags */
.feature-flag-row {
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
}
.feature-flag-row:last-of-type {
  border-bottom: none;
}
.feature-flag-label {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3, 12px);
}
.feature-flag-text-group {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}
.feature-flag-text {
  font-size: 13px;
  font-weight: 500;
}
.feature-flag-desc {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.4;
}
.feature-toggle {
  width: 40px;
  height: 22px;
  border-radius: 11px;
  background: var(--border);
  position: relative;
  cursor: pointer;
  transition: background 0.2s;
  flex-shrink: 0;
  border: none;
  padding: 0;
  outline-offset: 2px;
}
.feature-toggle.on {
  background: var(--accent);
}
.feature-toggle-knob {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #fff;
  position: absolute;
  top: 2px;
  left: 2px;
  transition: transform 0.2s;
}
.feature-toggle.on .feature-toggle-knob {
  transform: translateX(18px);
}

/* Provider management */
.providers-section {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.section-header {
  margin-bottom: var(--space-4, 16px);
}

.section-hint {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 4px;
  line-height: 1.5;
}

.provider-error {
  font-size: 12px;
  color: var(--danger);
  background: color-mix(in srgb, var(--danger) 8%, var(--surface));
  border: 1px solid color-mix(in srgb, var(--danger) 30%, var(--border));
  border-radius: var(--radius-sm, 8px);
  padding: 10px 14px;
  margin-top: var(--space-3, 12px);
}

.legacy-settings {
  margin-top: var(--space-4, 16px);
}

.legacy-settings-toggle {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-muted);
  cursor: pointer;
  padding: 10px 0;
  user-select: none;
  list-style: none;
  display: flex;
  align-items: center;
  gap: 6px;
}

.legacy-settings-toggle::-webkit-details-marker {
  display: none;
}

.legacy-settings-toggle::before {
  content: '>';
  display: inline-block;
  font-size: 11px;
  transition: transform var(--transition-fast);
}

.legacy-settings[open] > .legacy-settings-toggle::before {
  transform: rotate(90deg);
}
</style>
