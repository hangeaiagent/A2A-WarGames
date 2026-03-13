<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useProjectStore } from '../stores/projects'
import Modal from '../components/common/Modal.vue'

const { t } = useI18n()
const router = useRouter()
const store = useProjectStore()
const modal = ref(null)
const loading = ref(false)

const emptyForm = () => ({ name: '', description: '', organization: '', context: '' })
const form = ref(emptyForm())

onMounted(() => store.fetchProjects())

function openCreate() {
  form.value = emptyForm()
  modal.value = 'create'
}

function openEdit(p) {
  form.value = { ...p }
  modal.value = p
}

async function loadDemo() {
  loading.value = true
  try {
    await store.loadDemo()
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!form.value.name.trim()) return
  loading.value = true
  try {
    await store.saveProject(form.value)
    modal.value = null
    await store.fetchProjects()
  } finally {
    loading.value = false
  }
}

function goToStakeholders(p) {
  router.push(`/projects/${p.id}/stakeholders`)
}
</script>

<template>
  <div>
    <div class="page-header">
      <div>
        <div class="page-title">{{ t('projects.title') }}</div>
        <div class="page-subtitle">{{ t('projects.subtitle') }}</div>
      </div>
      <div style="display: flex; gap: 8px;">
        <button class="btn btn-ghost" @click="loadDemo" :disabled="loading">{{ t('projects.loadDemo') }}</button>
        <button class="btn btn-primary" @click="openCreate">{{ t('projects.newProject') }}</button>
      </div>
    </div>

    <div v-if="store.projects.length === 0" class="empty-state">
      <div style="font-size: 32px;">📁</div>
      <p>{{ t('projects.noProjects') }}</p>
    </div>
    <div v-else class="cards-grid">
      <div v-for="p in store.projects" :key="p.id" class="card" @click="goToStakeholders(p)">
        <div class="card-title">{{ p.name }}</div>
        <div v-if="p.organization" class="card-meta">{{ p.organization }}</div>
        <div class="card-meta" style="margin-top: 8px;">
          {{ p.stakeholder_count }} {{ t('projects.stakeholders') }} · {{ p.session_count }} {{ t('projects.sessions') }}
        </div>
        <div v-if="p.description" class="card-meta" style="margin-top: 6px; font-size: 12px;">
          {{ p.description.slice(0, 100) }}{{ p.description.length > 100 ? '…' : '' }}
        </div>
        <div style="margin-top: 10px;" @click.stop>
          <button class="btn btn-ghost" style="font-size: 11px; padding: 3px 10px;" @click="openEdit(p)">{{ t('projects.edit') }}</button>
        </div>
      </div>
    </div>

    <Modal v-if="modal" :title="modal === 'create' ? t('projects.newProjectTitle') : t('projects.editProjectTitle')" @close="modal = null">
      <div class="form-group">
        <label class="form-label">{{ t('projects.name') }}</label>
        <input class="form-input" v-model="form.name" />
      </div>
      <div class="form-group">
        <label class="form-label">{{ t('projects.organization') }}</label>
        <input class="form-input" v-model="form.organization" />
      </div>
      <div class="form-group">
        <label class="form-label">{{ t('projects.description') }}</label>
        <textarea class="form-textarea" v-model="form.description" />
      </div>
      <div class="form-group">
        <label class="form-label">{{ t('projects.orgContext') }}</label>
        <textarea class="form-textarea" style="min-height: 120px;" v-model="form.context" />
      </div>
      <div class="modal-actions">
        <button class="btn btn-ghost" @click="modal = null">{{ t('projects.cancel') }}</button>
        <button class="btn btn-primary" @click="save" :disabled="loading">{{ loading ? t('projects.saving') : t('projects.save') }}</button>
      </div>
    </Modal>
  </div>
</template>
