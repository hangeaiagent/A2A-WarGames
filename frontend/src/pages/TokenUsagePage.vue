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

const totalMessages = computed(() => sessions.value.reduce((sum, s) => sum + (s.message_count || 0), 0))
const sessionCount = computed(() => sessions.value.length)
const completedCount = computed(() => sessions.value.filter(s => s.status === 'complete').length)
const runningCount = computed(() => sessions.value.filter(s => s.status === 'running').length)
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
          <div class="stat-label">{{ t('tokenUsage.totalMessages') }}</div>
          <div class="stat-value">{{ totalMessages.toLocaleString() }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('tokenUsage.sessionCount') }}</div>
          <div class="stat-value">{{ sessionCount }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('tokenUsage.completedSessions') }}</div>
          <div class="stat-value">{{ completedCount }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('tokenUsage.runningSessions') }}</div>
          <div class="stat-value">{{ runningCount }}</div>
        </div>
      </div>

      <div v-if="sessions.length" class="session-breakdown">
        <h2 class="section-title">{{ t('tokenUsage.bySession') }}</h2>
        <table class="usage-table">
          <thead>
            <tr>
              <th>{{ t('tokenUsage.session') }}</th>
              <th>{{ t('tokenUsage.status') }}</th>
              <th>{{ t('tokenUsage.messages') }}</th>
              <th>{{ t('tokenUsage.date') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in sessions" :key="row.id">
              <td>{{ row.title || row.question || `#${row.id}` }}</td>
              <td><span class="status-badge" :class="`status-${row.status}`">{{ t(`status.${row.status || 'pending'}`) }}</span></td>
              <td>{{ row.message_count ?? 0 }}</td>
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
