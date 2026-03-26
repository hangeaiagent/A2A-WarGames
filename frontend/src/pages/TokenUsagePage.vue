<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import api from '../api/client.js'

const { t } = useI18n()
const loading = ref(true)
const sessions = ref([])
const error = ref('')

onMounted(async () => {
  try {
    const { data } = await api.get('/api/sessions/')
    sessions.value = data
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    loading.value = false
  }
})

const totalPrompt = computed(() => sessions.value.reduce((sum, s) => sum + (s.total_prompt_tokens || 0), 0))
const totalCompletion = computed(() => sessions.value.reduce((sum, s) => sum + (s.total_completion_tokens || 0), 0))
const totalTokens = computed(() => totalPrompt.value + totalCompletion.value)
const sessionCount = computed(() => sessions.value.length)
</script>

<template>
  <div class="page-container">
    <h1 class="page-title">{{ t('tokenUsage.title') }}</h1>
    <p class="page-subtitle">{{ t('tokenUsage.subtitle') }}</p>

    <div v-if="loading" class="loading-state">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error-state">{{ error }}</div>
    <div v-else class="usage-content">
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-label">{{ t('tokenUsage.totalTokens') }}</div>
          <div class="stat-value">{{ totalTokens.toLocaleString() }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('tokenUsage.promptTokens') }}</div>
          <div class="stat-value">{{ totalPrompt.toLocaleString() }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('tokenUsage.completionTokens') }}</div>
          <div class="stat-value">{{ totalCompletion.toLocaleString() }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('tokenUsage.sessionCount') }}</div>
          <div class="stat-value">{{ sessionCount }}</div>
        </div>
      </div>

      <div v-if="sessions.length" class="session-breakdown">
        <h2 class="section-title">{{ t('tokenUsage.bySession') }}</h2>
        <table class="usage-table">
          <thead>
            <tr>
              <th>{{ t('tokenUsage.session') }}</th>
              <th>{{ t('tokenUsage.promptTokens') }}</th>
              <th>{{ t('tokenUsage.completionTokens') }}</th>
              <th>{{ t('tokenUsage.totalTokens') }}</th>
              <th>{{ t('tokenUsage.date') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in sessions" :key="row.id">
              <td>{{ row.title || row.question || `#${row.id}` }}</td>
              <td>{{ (row.total_prompt_tokens || 0).toLocaleString() }}</td>
              <td>{{ (row.total_completion_tokens || 0).toLocaleString() }}</td>
              <td>{{ ((row.total_prompt_tokens || 0) + (row.total_completion_tokens || 0)).toLocaleString() }}</td>
              <td>{{ row.created_at ? new Date(row.created_at).toLocaleDateString() : '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-else class="empty-state">
        {{ t('tokenUsage.noData') }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-container {
  max-width: 900px;
  margin: 0 auto;
  padding: 32px 24px;
}
.page-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 4px;
}
.page-subtitle {
  font-size: 14px;
  color: var(--text-muted);
  margin-bottom: 24px;
}
.loading-state,
.error-state,
.empty-state {
  text-align: center;
  padding: 48px 0;
  color: var(--text-muted);
  font-size: 14px;
}
.error-state { color: var(--danger, #ef4444); }
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 16px;
  margin-bottom: 32px;
}
.stat-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  text-align: center;
}
.stat-label {
  font-size: 12px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 8px;
}
.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--text);
}
.section-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 12px;
}
.usage-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.usage-table th,
.usage-table td {
  padding: 10px 12px;
  text-align: left;
  border-bottom: 1px solid var(--border);
}
.usage-table th {
  color: var(--text-muted);
  font-weight: 600;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.usage-table td {
  color: var(--text);
}
</style>
