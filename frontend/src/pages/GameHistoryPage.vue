<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import api from '../api/client.js'

const { t } = useI18n()
const router = useRouter()
const loading = ref(true)
const games = ref([])
const error = ref('')

onMounted(async () => {
  try {
    const { data } = await api.get('/api/sessions')
    games.value = data
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  } finally {
    loading.value = false
  }
})

function statusClass(status) {
  return `status-${status || 'pending'}`
}

function goToSession(session) {
  if (session.status === 'complete') {
    router.push(`/sessions/${session.id}/analytics`)
  } else {
    router.push(`/sessions/${session.id}/live`)
  }
}
</script>

<template>
  <div class="page-container">
    <h1 class="page-title">{{ t('gameHistory.title') }}</h1>
    <p class="page-subtitle">{{ t('gameHistory.subtitle') }}</p>

    <div v-if="loading" class="loading-state">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error-state">{{ error }}</div>
    <div v-else-if="!games.length" class="empty-state">{{ t('gameHistory.noGames') }}</div>
    <div v-else class="game-list">
      <div
        v-for="game in games"
        :key="game.id"
        class="game-card"
        @click="goToSession(game)"
      >
        <div class="game-header">
          <span class="game-title">{{ game.title || game.question || `Session #${game.id}` }}</span>
          <span class="game-status" :class="statusClass(game.status)">{{ t(`status.${game.status || 'pending'}`) }}</span>
        </div>
        <div class="game-meta">
          <span v-if="game.project_name" class="meta-item">{{ game.project_name }}</span>
          <span class="meta-item">{{ t('gameHistory.participants', { count: game.participant_count ?? 0 }) }}</span>
          <span v-if="game.consensus_score != null" class="meta-item">{{ t('gameHistory.consensus') }}: {{ (game.consensus_score * 100).toFixed(0) }}%</span>
          <span class="meta-item">{{ game.created_at ? new Date(game.created_at).toLocaleDateString() : '-' }}</span>
        </div>
        <div v-if="game.question" class="game-question">{{ game.question }}</div>
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
.game-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.game-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px 20px;
  cursor: pointer;
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
}
.game-card:hover {
  border-color: var(--accent);
  box-shadow: var(--shadow);
}
.game-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.game-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
}
.game-status {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.status-complete { background: #dcfce7; color: #166534; }
.status-running { background: #dbeafe; color: #1e40af; }
.status-pending { background: #fef3c7; color: #92400e; }
.status-error, .status-failed { background: #fee2e2; color: #991b1b; }
.status-stopped, .status-interrupted { background: #f3f4f6; color: #4b5563; }
.status-paused { background: #e0e7ff; color: #3730a3; }
.game-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 6px;
}
.meta-item::before {
  content: '';
}
.game-question {
  font-size: 13px;
  color: var(--text-muted);
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
