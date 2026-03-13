<script setup>
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import api from '../api/client'
import { useSettingsStore } from '../stores/settings'

const { t } = useI18n()
const settingsStore = useSettingsStore()
const open = ref(false)
const activeTab = ref('enhance')
const loading = ref(false)

// Enhance tab state
const enhanceProjectId = ref('')
const enhanceText = ref('')
const enhanceTone = ref('professional')
const enhanceResult = ref(null)

// Extract tab state
const extractText = ref('')
const extractProjectId = ref('')
const extractResult = ref(null)

const projects = ref([])

async function fetchProjects() {
  try {
    const r = await api.get('/api/projects/')
    projects.value = r.data || []
  } catch (err) {
    console.warn('Failed to load projects for AI assistant:', err.message)
  }
}

function toggle() {
  open.value = !open.value
  if (open.value && projects.value.length === 0) {
    fetchProjects()
  }
}

async function enhance() {
  if (!enhanceText.value.trim() || !enhanceProjectId.value) return
  loading.value = true
  enhanceResult.value = null
  try {
    const r = await api.post('/api/assistant/enhance', {
      proposal_text: enhanceText.value,
      project_id: Number(enhanceProjectId.value),
      tone: enhanceTone.value,
    })
    enhanceResult.value = r.data
  } catch (err) {
    enhanceResult.value = { enhanced_text: err.response?.data?.detail || 'Error', key_changes: [] }
  } finally {
    loading.value = false
  }
}

async function extractProfile() {
  if (!extractText.value.trim()) return
  loading.value = true
  extractResult.value = null
  try {
    const r = await api.post('/api/assistant/extract-profile', {
      source_text: extractText.value,
      project_id: Number(extractProjectId.value) || 0,
    })
    extractResult.value = r.data
  } catch (err) {
    extractResult.value = { notes: err.response?.data?.detail || 'Error' }
  } finally {
    loading.value = false
  }
}

function copyText(text) {
  navigator.clipboard.writeText(text)
}
</script>

<template>
  <div class="ai-assistant">
    <button class="ai-fab" @click="toggle" :title="t('aiAssistant.title')">✦</button>

    <Transition name="slide">
      <div v-if="open" class="ai-panel">
        <div class="ai-panel-header">
          <span>{{ t('aiAssistant.title') }}</span>
          <button class="ai-close" @click="open = false">✕</button>
        </div>

        <div class="ai-tabs">
          <button :class="{ active: activeTab === 'enhance' }" @click="activeTab = 'enhance'">{{ t('aiAssistant.enhanceProposal') }}</button>
          <button :class="{ active: activeTab === 'extract' }" @click="activeTab = 'extract'">{{ t('aiAssistant.extractProfile') }}</button>
        </div>

        <!-- Enhance Proposal Tab -->
        <div v-if="activeTab === 'enhance'" class="ai-tab-content">
          <label>{{ t('aiAssistant.project') }}</label>
          <select v-model="enhanceProjectId" class="ai-select">
            <option value="" disabled>{{ t('aiAssistant.selectProject') }}</option>
            <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>

          <label>{{ t('aiAssistant.proposalText') }}</label>
          <textarea v-model="enhanceText" :placeholder="t('aiAssistant.proposalPlaceholder')" rows="6" class="ai-textarea" />

          <label>{{ t('aiAssistant.tone') }}</label>
          <select v-model="enhanceTone" class="ai-select">
            <option value="professional">{{ t('aiAssistant.professional') }}</option>
            <option value="technical">{{ t('aiAssistant.technical') }}</option>
            <option value="executive">{{ t('aiAssistant.executive') }}</option>
          </select>

          <button class="ai-btn" @click="enhance" :disabled="loading || !enhanceText.trim() || !enhanceProjectId">
            {{ loading ? t('aiAssistant.enhancing') : t('aiAssistant.enhance') }}
          </button>

          <div v-if="enhanceResult" class="ai-result">
            <div class="ai-result-header">
              <strong>{{ t('aiAssistant.enhancedText') }}</strong>
              <button class="ai-copy" @click="copyText(enhanceResult.enhanced_text)">{{ t('aiAssistant.copy') }}</button>
            </div>
            <pre class="ai-code">{{ enhanceResult.enhanced_text }}</pre>
            <div v-if="enhanceResult.key_changes?.length">
              <strong>{{ t('aiAssistant.keyChanges') }}</strong>
              <ul>
                <li v-for="(c, i) in enhanceResult.key_changes" :key="i">{{ c }}</li>
              </ul>
            </div>
          </div>
        </div>

        <!-- Extract Profile Tab -->
        <div v-if="activeTab === 'extract'" class="ai-tab-content">
          <label>{{ t('aiAssistant.sourceText') }}</label>
          <textarea v-model="extractText" :placeholder="t('aiAssistant.sourcePlaceholder')" rows="6" class="ai-textarea" />

          <label>{{ t('aiAssistant.projectOptional') }}</label>
          <select v-model="extractProjectId" class="ai-select">
            <option value="">{{ t('aiAssistant.none') }}</option>
            <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>

          <button class="ai-btn" @click="extractProfile" :disabled="loading || !extractText.trim()">
            {{ loading ? t('aiAssistant.extracting') : t('aiAssistant.extractProfileBtn') }}
          </button>

          <div v-if="extractResult" class="ai-result">
            <div class="ai-field" v-if="extractResult.name"><strong>{{ t('aiAssistant.resultName') }}</strong> {{ extractResult.name }}</div>
            <div class="ai-field" v-if="extractResult.role"><strong>{{ t('aiAssistant.resultRole') }}</strong> {{ extractResult.role }}</div>
            <div class="ai-field" v-if="extractResult.department"><strong>{{ t('aiAssistant.resultDepartment') }}</strong> {{ extractResult.department }}</div>
            <div class="ai-field" v-if="extractResult.goals"><strong>{{ t('aiAssistant.resultGoals') }}</strong> {{ extractResult.goals }}</div>
            <div class="ai-field" v-if="extractResult.fears"><strong>{{ t('aiAssistant.resultFears') }}</strong> {{ extractResult.fears }}</div>
            <div class="ai-field"><strong>{{ t('aiAssistant.resultInfluence') }}</strong> {{ extractResult.influence }}</div>
            <div class="ai-field"><strong>{{ t('aiAssistant.resultAttitude') }}</strong> {{ extractResult.attitude_label }}</div>
            <div class="ai-field" v-if="extractResult.key_motivations?.length">
              <strong>{{ t('aiAssistant.resultMotivations') }}</strong>
              <ul><li v-for="(m, i) in extractResult.key_motivations" :key="i">{{ m }}</li></ul>
            </div>
            <div class="ai-field" v-if="extractResult.success_criteria?.length">
              <strong>{{ t('aiAssistant.resultSuccessCriteria') }}</strong>
              <ul><li v-for="(c, i) in extractResult.success_criteria" :key="i">{{ c }}</li></ul>
            </div>
            <div class="ai-field" v-if="extractResult.notes"><strong>{{ t('aiAssistant.resultNotes') }}</strong> {{ extractResult.notes }}</div>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.ai-fab {
  position: fixed;
  bottom: 48px;
  right: 24px;
  z-index: 900;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: var(--accent, #7c3aed);
  color: white;
  border: none;
  font-size: 20px;
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(0,0,0,0.3);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.15s;
}
.ai-fab:hover { transform: scale(1.1); }

.ai-panel {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  width: 380px;
  z-index: 901;
  background: var(--surface, #1e1e2e);
  border-left: 1px solid var(--border, #333);
  display: flex;
  flex-direction: column;
  box-shadow: -4px 0 16px rgba(0,0,0,0.3);
  overflow-y: auto;
}

.ai-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border, #333);
  font-weight: 600;
  font-size: 14px;
}
.ai-close {
  background: none;
  border: none;
  color: var(--text-muted, #aaa);
  font-size: 16px;
  cursor: pointer;
}
.ai-close:hover { color: var(--text, #fff); }

.ai-tabs {
  display: flex;
  border-bottom: 1px solid var(--border, #333);
}
.ai-tabs button {
  flex: 1;
  padding: 8px;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-muted, #aaa);
  cursor: pointer;
  font-size: 12px;
}
.ai-tabs button.active {
  color: var(--accent, #7c3aed);
  border-bottom-color: var(--accent, #7c3aed);
}

.ai-tab-content {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ai-tab-content label {
  font-size: 11px;
  color: var(--text-muted, #aaa);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.ai-select, .ai-textarea {
  width: 100%;
  padding: 8px;
  background: var(--surface-alt, #2a2a3e);
  color: var(--text, #e0e0e0);
  border: 1px solid var(--border, #333);
  border-radius: 6px;
  font-size: 13px;
  font-family: inherit;
}
.ai-textarea { resize: vertical; }

.ai-btn {
  padding: 8px 16px;
  background: var(--accent, #7c3aed);
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  margin-top: 4px;
}
.ai-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.ai-btn:hover:not(:disabled) { opacity: 0.9; }

.ai-result {
  margin-top: 12px;
  padding: 12px;
  background: var(--surface-alt, #2a2a3e);
  border-radius: 6px;
  font-size: 13px;
}
.ai-result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.ai-copy {
  padding: 2px 8px;
  background: var(--border, #333);
  color: var(--text, #e0e0e0);
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 11px;
}
.ai-copy:hover { background: var(--accent, #7c3aed); color: white; }

.ai-code {
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--surface, #1e1e2e);
  padding: 8px;
  border-radius: 4px;
  font-size: 12px;
  max-height: 200px;
  overflow-y: auto;
}

.ai-field {
  margin-bottom: 6px;
  font-size: 13px;
}
.ai-field ul {
  margin: 4px 0 0 16px;
  padding: 0;
}

.slide-enter-active, .slide-leave-active {
  transition: transform 0.25s ease;
}
.slide-enter-from, .slide-leave-to {
  transform: translateX(100%);
}
</style>
