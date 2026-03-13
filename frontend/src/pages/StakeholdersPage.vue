<script setup>
import { ref, inject, watch, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../stores/auth'
import { useProjectStore } from '../stores/projects'
import { useProvidersStore } from '../stores/providers'
import Modal from '../components/common/Modal.vue'
import AdkarSliders from '../components/stakeholder/AdkarSliders.vue'
import SimParamsSection from '../components/stakeholder/SimParamsSection.vue'
import LlmOverrideSection from '../components/stakeholder/LlmOverrideSection.vue'

const route = useRoute()
const auth = useAuthStore()
const store = useProjectStore()
const providersStore = useProvidersStore()
const { t } = useI18n()
const showLogin = inject('showLogin')
const isReadOnly = computed(() => auth.isGuest || store.currentProject?.is_demo)

const projectId = computed(() => Number(route.params.projectId))
const modal = ref(null)
const expanded = ref(null)
const loading = ref(false)
const advancedOpen = ref(false)

const ATTITUDES = ['founder', 'enthusiast', 'conditional', 'strategic', 'critical', 'neutral']
const SALIENCE_TYPES = ['definitive', 'dependent', 'dominant', 'dormant', 'dangerous', 'discretionary', 'demanding']
const MENDELOW_QUADRANTS = ['manage_closely', 'keep_satisfied', 'keep_informed', 'monitor']

const emptyForm = () => ({
  slug: '', name: '', role: '', department: '', attitude: 'neutral', attitude_label: '',
  influence: 0.5, interest: 0.5, needs: [], fears: [], quote: '', signal_cle: '',
  adkar: { awareness: 3, desire: 3, knowledge: 3, ability: 3, reinforcement: 3 },
  color: '#888888', llm_model: '', llm_provider: '', llm_model_display: '', system_prompt: '',
  sim_params: { max_turns_per_round: 3, max_tokens: 1024, is_silenced: false, speaking_priority: 1.0, temperature: 0.7 },
  salience_power: 5, salience_legitimacy: 5, salience_urgency: 5,
  salience_type: '', mendelow_quadrant: '',
  communication_style: '', attitude_baseline: '', interest_alignment: 0,
  cognitive_biases: [],
  batna: '',
  hard_constraints: [],
  success_criteria: [],
  key_concerns: [],
  grounding_quotes: [],
  anti_sycophancy: '',
})

const form = ref(emptyForm())

function getModelBadge(s) {
  if (!s.llm_provider || !s.llm_model) return null
  const preset = providersStore.getPresetById(s.llm_provider)
  const icon = preset?.icon || ''
  const display = s.llm_model_display || s.llm_model
  return `${icon} ${display}`.trim()
}

onMounted(async () => {
  await store.fetchProjects()
  providersStore.fetchPresets()
  if (projectId.value) {
    await store.fetchStakeholders(projectId.value)
    store.setCurrentProject(store.projects.find(p => p.id === projectId.value) || null)
  }
})

watch(projectId, async (id) => {
  if (id) {
    await store.fetchStakeholders(id)
    store.setCurrentProject(store.projects.find(p => p.id === id) || null)
  }
})

function needsStr(arr) { return (arr || []).join(', ') }
function parseList(str) { return str.split(',').map(s => s.trim()).filter(Boolean) }
function linesStr(arr) { return (arr || []).join('\n') }
function parseLines(str) { return str.split('\n').map(s => s.trim()).filter(Boolean) }

function adkarAvg(s) {
  if (!s.adkar) return '—'
  return (Object.values(s.adkar).reduce((a, b) => a + b, 0) / 5).toFixed(1)
}

function openCreate() {
  form.value = emptyForm()
  advancedOpen.value = false
  modal.value = 'create'
}

function openEdit(s) {
  form.value = {
    ...s,
    needs: s.needs || [],
    fears: s.fears || [],
    llm_model: s.llm_model || '',
    llm_provider: s.llm_provider || '',
    llm_model_display: s.llm_model_display || '',
    system_prompt: s.system_prompt || '',
    sim_params: s.sim_params || emptyForm().sim_params,
    salience_power: s.salience_power ?? 5,
    salience_legitimacy: s.salience_legitimacy ?? 5,
    salience_urgency: s.salience_urgency ?? 5,
    salience_type: s.salience_type || '',
    mendelow_quadrant: s.mendelow_quadrant || '',
    communication_style: s.communication_style || '',
    attitude_baseline: s.attitude_baseline || '',
    interest_alignment: s.interest_alignment ?? 0,
    cognitive_biases: s.cognitive_biases || [],
    batna: s.batna || '',
    hard_constraints: s.hard_constraints || [],
    success_criteria: s.success_criteria || [],
    key_concerns: s.key_concerns || [],
    grounding_quotes: s.grounding_quotes || [],
    anti_sycophancy: s.anti_sycophancy || '',
  }
  advancedOpen.value = false
  modal.value = s
}

async function save() {
  if (!form.value.name.trim() || !form.value.slug.trim()) return
  loading.value = true
  try {
    const payload = {
      ...form.value,
      llm_model: form.value.llm_model || null,
      llm_provider: form.value.llm_provider || null,
      llm_model_display: form.value.llm_model_display || null,
      system_prompt: form.value.system_prompt || null,
    }
    await store.saveStakeholder(projectId.value, payload)
    modal.value = null
    await store.fetchStakeholders(projectId.value)
  } finally {
    loading.value = false
  }
}

async function remove(s) {
  if (!confirm(t('stakeholders.removeConfirm', { name: s.name }))) return
  await store.removeStakeholder(projectId.value, s.id)
  await store.fetchStakeholders(projectId.value)
}
</script>

<template>
  <div>
    <div class="page-header">
      <div>
        <div class="page-title">
          {{ t('stakeholders.title') }}
          <span v-if="store.currentProject" style="color: var(--text-muted); font-size: 16px; font-weight: 400;"> — {{ store.currentProject.name }}</span>
        </div>
        <div class="page-subtitle">{{ t('stakeholders.subtitle') }}</div>
      </div>
      <button v-if="!isReadOnly" class="btn btn-primary" @click="openCreate">{{ t('stakeholders.addStakeholder') }}</button>
      <span v-else-if="auth.isGuest" class="text-muted" style="font-size: 12px; cursor: pointer;" @click="showLogin = true">🔒 {{ t('guest.signInToEdit') }}</span>
    </div>

    <div v-if="store.stakeholders.length === 0" class="empty-state">
      <div style="font-size: 32px;">👤</div>
      <p>{{ t('stakeholders.noStakeholders') }}</p>
    </div>
    <table v-else class="data-table">
      <thead>
        <tr>
          <th>{{ t('stakeholders.name') }}</th><th>{{ t('stakeholders.role') }}</th><th>{{ t('stakeholders.attitude') }}</th><th>{{ t('stakeholders.influence') }}</th><th>{{ t('stakeholders.adkarAvg') }}</th><th>{{ t('stakeholders.actions') }}</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="s in store.stakeholders" :key="s.id">
          <tr style="cursor: pointer;" @click="expanded = expanded === s.id ? null : s.id">
            <td>
              <span class="influence-dot" :style="{ background: s.color }" />
              <strong>{{ s.name }}</strong>
              <span v-if="getModelBadge(s)" class="model-badge" :title="t('stakeholders.llmOverride.badge')">{{ getModelBadge(s) }}</span>
            </td>
            <td style="color: var(--text-muted);">{{ s.role }}</td>
            <td>
              <span :class="['card-badge', `att-${s.attitude}`]">{{ s.attitude_label || s.attitude }}</span>
            </td>
            <td>{{ Math.round(s.influence * 100) }}%</td>
            <td>{{ adkarAvg(s) }}/5</td>
            <td @click.stop style="display: flex; gap: 6px;">
              <template v-if="!isReadOnly">
                <button class="btn btn-ghost" style="margin-right: 6px;" @click="openEdit(s)">{{ t('stakeholders.edit') }}</button>
                <button class="btn btn-danger btn-icon" :aria-label="t('stakeholders.removeStakeholder', { name: s.name })" @click="remove(s)">×</button>
              </template>
              <span v-else style="font-size: 11px; color: var(--text-muted);">{{ t('guest.readOnly') }}</span>
            </td>
          </tr>
          <tr v-if="expanded === s.id" :key="`${s.id}-exp`">
            <td colspan="6" class="stakeholder-expanded-cell">
              <blockquote v-if="s.quote" :style="{ borderLeft: `3px solid ${s.color}`, paddingLeft: '12px', marginBottom: '12px', fontStyle: 'italic', color: 'var(--text-muted)' }">
                {{ s.quote }}
              </blockquote>
              <p v-if="s.signal_cle" style="margin-bottom: 12px; font-size: 13px;">{{ s.signal_cle }}</p>
              <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                <div>
                  <div class="section-title">{{ t('stakeholders.needs') }}</div>
                  <div class="tag-list">
                    <span v-for="n in (s.needs || [])" :key="n" class="tag">{{ n }}</span>
                  </div>
                  <div class="section-title">{{ t('stakeholders.fears') }}</div>
                  <div class="tag-list">
                    <span v-for="f in (s.fears || [])" :key="f" class="tag fear-tag">{{ f }}</span>
                  </div>
                </div>
                <div>
                  <div class="section-title">{{ t('stakeholders.adkarScoresShort') }}</div>
                  <div v-for="dim in ['awareness','desire','knowledge','ability','reinforcement']" :key="dim" class="adkar-row">
                    <span class="adkar-label">{{ dim.charAt(0).toUpperCase() + dim.slice(1) }}</span>
                    <div class="adkar-bar-bg">
                      <div class="adkar-bar-fill" :style="{ width: `${((s.adkar?.[dim] || 0) / 5) * 100}%` }" />
                    </div>
                    <span style="font-size: 11px; color: var(--text-muted); width: 14px;">{{ s.adkar?.[dim] || 0 }}</span>
                  </div>
                </div>
              </div>
            </td>
          </tr>
        </template>
      </tbody>
    </table>

    <Modal v-if="modal" :title="modal === 'create' ? t('stakeholders.newStakeholder') : t('stakeholders.editStakeholder', { name: modal.name })" :width="640" @close="modal = null">
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
        <div class="form-group">
          <label class="form-label">{{ t('stakeholders.slug') }}</label>
          <input class="form-input" v-model="form.slug" @input="form.slug = form.slug.toLowerCase().replace(/\s/g, '-')" />
        </div>
        <div class="form-group">
          <label class="form-label">{{ t('stakeholders.nameStar') }}</label>
          <input class="form-input" v-model="form.name" />
        </div>
        <div class="form-group">
          <label class="form-label">{{ t('stakeholders.role') }}</label>
          <input class="form-input" v-model="form.role" />
        </div>
        <div class="form-group">
          <label class="form-label">{{ t('stakeholders.department') }}</label>
          <input class="form-input" v-model="form.department" />
        </div>
        <div class="form-group">
          <label class="form-label">{{ t('stakeholders.attitude') }}</label>
          <select class="form-select" v-model="form.attitude">
            <option v-for="a in ATTITUDES" :key="a" :value="a">{{ a }}</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">{{ t('stakeholders.color') }}</label>
          <input type="color" v-model="form.color" style="width: 100%; height: 38px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg); cursor: pointer;" />
        </div>
        <div class="form-group">
          <label class="form-label">{{ t('stakeholders.influenceRange') }}</label>
          <input type="number" min="0" max="1" step="0.05" class="form-input" v-model.number="form.influence" />
        </div>
        <div class="form-group">
          <label class="form-label">{{ t('stakeholders.interestRange') }}</label>
          <input type="number" min="0" max="1" step="0.05" class="form-input" v-model.number="form.interest" />
        </div>
      </div>

      <div class="form-group">
        <label class="form-label">{{ t('stakeholders.needs') }}</label>
        <input class="form-input" :value="needsStr(form.needs)" @input="form.needs = parseList($event.target.value)" />
      </div>
      <div class="form-group">
        <label class="form-label">{{ t('stakeholders.fears') }}</label>
        <input class="form-input" :value="needsStr(form.fears)" @input="form.fears = parseList($event.target.value)" />
      </div>
      <div class="form-group">
        <label class="form-label">{{ t('stakeholders.keyQuote') }}</label>
        <textarea class="form-textarea" v-model="form.quote" />
      </div>
      <div class="form-group">
        <label class="form-label">{{ t('stakeholders.keySignal') }}</label>
        <textarea class="form-textarea" v-model="form.signal_cle" />
      </div>

      <div class="section-title">{{ t('stakeholders.adkarScores') }}</div>
      <AdkarSliders v-model="form.adkar" />

      <!-- Advanced Profile (collapsible) -->
      <div class="section-title" style="cursor: pointer; user-select: none; display: flex; align-items: center; gap: 8px;" @click="advancedOpen = !advancedOpen">
        <span>{{ advancedOpen ? '▾' : '▸' }}</span> {{ t('stakeholders.advancedProfile') }}
      </div>
      <div v-if="advancedOpen">
        <div class="section-title" style="margin-top: 8px;">{{ t('stakeholders.salience') }}</div>
        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px;">
          <div class="form-group">
            <label class="form-label">{{ t('stakeholders.power') }}</label>
            <input type="range" min="1" max="10" class="form-input" style="padding: 4px;" v-model.number="form.salience_power" />
            <span style="font-size: 11px; color: var(--text-muted);">{{ form.salience_power }}</span>
          </div>
          <div class="form-group">
            <label class="form-label">{{ t('stakeholders.legitimacy') }}</label>
            <input type="range" min="1" max="10" class="form-input" style="padding: 4px;" v-model.number="form.salience_legitimacy" />
            <span style="font-size: 11px; color: var(--text-muted);">{{ form.salience_legitimacy }}</span>
          </div>
          <div class="form-group">
            <label class="form-label">{{ t('stakeholders.urgency') }}</label>
            <input type="range" min="1" max="10" class="form-input" style="padding: 4px;" v-model.number="form.salience_urgency" />
            <span style="font-size: 11px; color: var(--text-muted);">{{ form.salience_urgency }}</span>
          </div>
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
          <div class="form-group">
            <label class="form-label">{{ t('stakeholders.salienceType') }}</label>
            <select class="form-select" v-model="form.salience_type">
              <option value="">{{ t('stakeholders.select') }}</option>
              <option v-for="st in SALIENCE_TYPES" :key="st" :value="st">{{ st }}</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">{{ t('stakeholders.mendelowQuadrant') }}</label>
            <select class="form-select" v-model="form.mendelow_quadrant">
              <option value="">{{ t('stakeholders.select') }}</option>
              <option v-for="q in MENDELOW_QUADRANTS" :key="q" :value="q">{{ q }}</option>
            </select>
          </div>
        </div>

        <div class="section-title">{{ t('stakeholders.behavioralProfile') }}</div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
          <div class="form-group">
            <label class="form-label">{{ t('stakeholders.communicationStyle') }}</label>
            <input class="form-input" v-model="form.communication_style" placeholder="e.g. direct_paternal_pragmatic" />
          </div>
          <div class="form-group">
            <label class="form-label">{{ t('stakeholders.attitudeBaseline') }}</label>
            <input class="form-input" v-model="form.attitude_baseline" placeholder="e.g. pragmatic_cautious" />
          </div>
        </div>
        <div class="form-group">
          <label class="form-label">{{ t('stakeholders.interestAlignment') }}</label>
          <input type="range" min="-5" max="5" step="1" class="form-input" style="padding: 4px;" v-model.number="form.interest_alignment" />
          <span style="font-size: 11px; color: var(--text-muted);">{{ form.interest_alignment }}</span>
        </div>
        <div class="form-group">
          <label class="form-label">{{ t('stakeholders.cognitiveBiases') }}</label>
          <input class="form-input" :value="needsStr(form.cognitive_biases)" @input="form.cognitive_biases = parseList($event.target.value)" placeholder="e.g. status_quo_bias, loss_aversion" />
          <div class="tag-list" style="margin-top: 6px;">
            <span v-for="b in (form.cognitive_biases || [])" :key="b" class="tag">{{ b }}</span>
          </div>
        </div>

        <div class="section-title">{{ t('stakeholders.strategicProfile') }}</div>
        <div class="form-group">
          <label class="form-label">{{ t('stakeholders.batna') }}</label>
          <textarea class="form-textarea" v-model="form.batna" :placeholder="t('stakeholders.batnaPlaceholder')" />
        </div>
        <div class="form-group">
          <label class="form-label">{{ t('stakeholders.hardConstraints') }}</label>
          <textarea class="form-textarea" style="min-height: 100px;" :value="linesStr(form.hard_constraints)" @input="form.hard_constraints = parseLines($event.target.value)" />
        </div>
        <div class="form-group">
          <label class="form-label">{{ t('stakeholders.successCriteria') }}</label>
          <textarea class="form-textarea" style="min-height: 80px;" :value="linesStr(form.success_criteria)" @input="form.success_criteria = parseLines($event.target.value)" />
        </div>
        <div class="form-group">
          <label class="form-label">{{ t('stakeholders.keyConcerns') }}</label>
          <textarea class="form-textarea" style="min-height: 100px;" :value="linesStr(form.key_concerns)" @input="form.key_concerns = parseLines($event.target.value)" />
        </div>

        <div class="section-title">{{ t('stakeholders.grounding') }}</div>
        <div class="form-group">
          <label class="form-label">{{ t('stakeholders.groundingQuotes') }}</label>
          <textarea class="form-textarea" style="min-height: 80px;" :value="linesStr(form.grounding_quotes)" @input="form.grounding_quotes = parseLines($event.target.value)" />
        </div>
        <div class="form-group">
          <label class="form-label">{{ t('stakeholders.antiSycophancy') }}</label>
          <textarea class="form-textarea" style="min-height: 120px;" v-model="form.anti_sycophancy" :placeholder="t('stakeholders.antiSycophancyPlaceholder')" />
        </div>
      </div>

      <div class="section-title">{{ t('stakeholders.agentOverride') }}</div>
      <LlmOverrideSection
        :llm-provider="form.llm_provider"
        :llm-model="form.llm_model"
        :llm-model-display="form.llm_model_display"
        @update:llm-provider="form.llm_provider = $event"
        @update:llm-model="form.llm_model = $event"
        @update:llm-model-display="form.llm_model_display = $event"
      />
      <div class="form-group" style="margin-top: 12px;">
        <label class="form-label">{{ t('stakeholders.systemPromptOverride') }}</label>
        <textarea class="form-textarea" style="min-height: 100px;" v-model="form.system_prompt" :placeholder="t('stakeholders.systemPromptPlaceholder')" />
      </div>

      <SimParamsSection v-model="form.sim_params" />

      <div class="modal-actions">
        <button class="btn btn-ghost" @click="modal = null">{{ t('stakeholders.cancel') }}</button>
        <button class="btn btn-primary" @click="save" :disabled="loading">{{ loading ? t('stakeholders.saving') : t('stakeholders.save') }}</button>
      </div>
    </Modal>
  </div>
</template>
