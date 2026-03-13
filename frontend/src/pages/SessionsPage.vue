<script setup>
import { ref, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useProjectStore } from '../stores/projects'
import { useSessionStore } from '../stores/sessions'
import Modal from '../components/common/Modal.vue'
import ConfirmDialog from '../components/common/ConfirmDialog.vue'
import StatusBadge from '../components/common/StatusBadge.vue'

const { t } = useI18n()
const router = useRouter()
const projectStore = useProjectStore()
const sessionStore = useSessionStore()

const selectedProjectId = ref(null)
const modal = ref(false)
const loading = ref(false)
const confirmDelete = ref(false)
const sessionToDelete = ref(null)

function formatParticipants(slugs) {
  if (!slugs || slugs.length === 0) return '—'
  const names = slugs.map(s => {
    const stk = projectStore.stakeholders?.find(x => x.slug === s)
    return stk?.name || s.replace(/-/g, ' ')
  })
  if (names.length > 3) return names.slice(0, 3).join(', ') + ` +${names.length - 3} more`
  return names.join(', ')
}

const newForm = ref({ question: '', title: '', participants: [] })
const stakeholders = ref([])

onMounted(async () => {
  await projectStore.fetchProjects()
  if (projectStore.projects.length) {
    selectedProjectId.value = projectStore.projects[0].id
  }
})

watch(selectedProjectId, async (id) => {
  if (id) {
    await sessionStore.fetchSessions(id)
    await projectStore.fetchStakeholders(id)
  }
})

async function openCreate() {
  if (!selectedProjectId.value) return
  const r = await projectStore.fetchStakeholders(selectedProjectId.value)
  stakeholders.value = r
  newForm.value = {
    question: '',
    title: '',
    participants: r.map(s => s.slug),
  }
  modal.value = true
}

function toggleParticipant(slug) {
  const idx = newForm.value.participants.indexOf(slug)
  if (idx >= 0) newForm.value.participants.splice(idx, 1)
  else newForm.value.participants.push(slug)
}

async function createSession() {
  if (!newForm.value.question.trim()) return
  loading.value = true
  try {
    await sessionStore.createNewSession({
      project_id: selectedProjectId.value,
      question: newForm.value.question,
      title: newForm.value.title,
      participants: newForm.value.participants,
    })
    modal.value = false
    await sessionStore.fetchSessions(selectedProjectId.value)
  } finally {
    loading.value = false
  }
}

function remove(s) {
  sessionToDelete.value = s
  confirmDelete.value = true
}

async function confirmRemove() {
  if (!sessionToDelete.value) return
  await sessionStore.removeSession(sessionToDelete.value.id)
  await sessionStore.fetchSessions(selectedProjectId.value)
  confirmDelete.value = false
  sessionToDelete.value = null
}

function launch(s) {
  router.push(`/sessions/${s.id}/live`)
}
</script>

<template>
  <div>
    <div class="page-header">
      <div>
        <div class="page-title">{{ t('sessions.title') }}</div>
        <div class="page-subtitle">{{ t('sessions.subtitle') }}</div>
      </div>
      <div style="display: flex; gap: 10px;">
        <select class="form-select" style="width: 220px;" v-model="selectedProjectId">
          <option v-for="p in projectStore.projects" :key="p.id" :value="p.id">{{ p.name }}</option>
        </select>
        <button class="btn btn-primary" @click="openCreate" :disabled="!selectedProjectId">{{ t('sessions.newSession') }}</button>
      </div>
    </div>

    <div v-if="sessionStore.sessions.length === 0" class="empty-state">
      <div style="font-size: 32px;">⚔</div>
      <p>{{ t('sessions.noSessions') }}</p>
    </div>
    <table v-else class="data-table">
      <thead>
        <tr><th>{{ t('sessions.titleColumn') }}</th><th>{{ t('sessions.status') }}</th><th>{{ t('sessions.participants') }}</th><th>{{ t('sessions.consensus') }}</th><th>{{ t('sessions.created') }}</th><th></th></tr>
      </thead>
      <tbody>
        <tr v-for="s in sessionStore.sessions" :key="s.id" style="cursor: pointer;">
          <td><strong>{{ s.title }}</strong></td>
          <td><StatusBadge :status="s.status" /></td>
          <td style="color: var(--text-muted);">{{ formatParticipants(s.participants) }}</td>
          <td>{{ s.consensus_score != null ? `${(s.consensus_score * 100).toFixed(0)}%` : '—' }}</td>
          <td style="color: var(--text-muted);">{{ new Date(s.created_at).toLocaleDateString() }}</td>
          <td style="display: flex; gap: 6px;">
            <button class="btn btn-primary" style="font-size: 11px; padding: 4px 10px;" @click="launch(s)">{{ t('sessions.launch') }}</button>
            <button v-if="s.status === 'complete'" class="btn btn-ghost" style="font-size: 11px; padding: 4px 10px;"
              @click="$router.push(`/sessions/${s.id}/analytics`)">{{ t('sessions.analytics') }}</button>
            <button class="btn btn-danger btn-icon" :aria-label="t('sessions.deleteSession')" @click="remove(s)">×</button>
          </td>
        </tr>
      </tbody>
    </table>

    <ConfirmDialog
      v-if="confirmDelete"
      :message="t('sessions.deleteConfirm')"
      @confirm="confirmRemove"
      @cancel="confirmDelete = false; sessionToDelete = null"
    />

    <Modal v-if="modal" :title="t('sessions.newWargameSession')" :width="560" @close="modal = false">
      <div class="form-group">
        <label class="form-label">{{ t('sessions.strategicQuestion') }}</label>
        <textarea class="form-textarea" style="min-height: 100px;" v-model="newForm.question"
          :placeholder="t('sessions.strategicQuestionPlaceholder')" />
      </div>
      <div class="form-group">
        <label class="form-label">{{ t('sessions.sessionTitle') }}</label>
        <input class="form-input" v-model="newForm.title" :placeholder="t('sessions.sessionTitlePlaceholder')" />
      </div>
      <div class="form-group">
        <label class="form-label">{{ t('sessions.participants') }}</label>
        <div style="display: flex; flex-wrap: wrap; gap: 8px; margin-top: 4px;">
          <button v-for="s in stakeholders" :key="s.slug" type="button" class="btn"
            :style="{
              background: newForm.participants.includes(s.slug) ? s.color : 'var(--surface)',
              color: newForm.participants.includes(s.slug) ? '#fff' : 'var(--text-muted)',
              border: `1px solid ${s.color}`,
              fontSize: '12px',
            }"
            @click="toggleParticipant(s.slug)">
            {{ s.name }}
          </button>
        </div>
      </div>
      <div class="modal-actions">
        <button class="btn btn-ghost" @click="modal = false">{{ t('sessions.cancel') }}</button>
        <button class="btn btn-primary" @click="createSession" :disabled="loading || !newForm.question.trim()">
          {{ loading ? t('sessions.creating') : t('sessions.createSession') }}
        </button>
      </div>
    </Modal>
  </div>
</template>
