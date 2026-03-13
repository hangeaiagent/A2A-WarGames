<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useSessionStore } from '../stores/sessions'
import VotingMatrix from '../components/metrics/VotingMatrix.vue'
import api from '../api/client'
import { Line } from 'vue-chartjs'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend)

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const store = useSessionStore()

const sessionId = computed(() => Number(route.params.sessionId))
const loading = ref(true)
const error = ref(null)
const votingItems = ref([])

onMounted(async () => {
  try {
    await store.fetchSession(sessionId.value)
    await store.fetchAnalytics(sessionId.value)
    try {
      const r = await api.get(`/api/sessions/${sessionId.value}/voting-summary`)
      votingItems.value = r.data.items || []
    } catch { /* S-BERT or agenda not available — skip silently */ }
  } catch {
    error.value = t('analyticsPage.error')
  } finally {
    loading.value = false
  }
})

const analytics = computed(() => store.analyticsData)

// Resolve CSS variable values for chart.js (which cannot use CSS vars directly)
function getCSSVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

const consensusChartData = computed(() => {
  if (!analytics.value?.consensus_trajectory) return null
  const accent = getCSSVar('--accent') || '#e94560'
  return {
    labels: analytics.value.consensus_trajectory.map((_, i) => `R${i + 1}`),
    datasets: [{
      label: 'Consensus',
      data: analytics.value.consensus_trajectory,
      borderColor: accent,
      backgroundColor: getCSSVar('--accent-glow') || 'rgba(233,69,96,0.1)',
      tension: 0.3,
      fill: true,
    }],
  }
})

const chartOptions = computed(() => {
  const textMuted = getCSSVar('--text-muted') || '#999999'
  const border = getCSSVar('--border') || '#16213e'
  return {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      y: { min: 0, max: 1, ticks: { color: textMuted }, grid: { color: border } },
      x: { ticks: { color: textMuted }, grid: { color: border } },
    },
    plugins: { legend: { display: false } },
  }
})

function riskColor(level) {
  if (level === 'HIGH') return 'var(--danger)'
  if (level === 'MEDIUM') return 'var(--warn)'
  return 'var(--success)'
}
</script>

<template>
  <div>
    <div class="page-header">
      <div>
        <div class="page-title">{{ t('analyticsPage.title', { title: store.currentSession?.title || '' }) }}</div>
        <div class="page-subtitle">{{ t('analyticsPage.subtitle') }}</div>
      </div>
      <button class="btn btn-ghost" @click="router.push('/sessions')">{{ t('analyticsPage.backArrow') }}</button>
    </div>

    <div v-if="loading" class="empty-state"><p>{{ t('analyticsPage.loading') }}</p></div>
    <div v-else-if="error" class="empty-state"><p>{{ error }}</p></div>
    <div v-else-if="!analytics" class="empty-state"><p>{{ t('analyticsPage.noData') }}</p></div>
    <div v-else>

      <div class="panel-box stat-grid">
        <div class="stat-card">
          <div class="stat-value" style="color: var(--accent);">
            {{ analytics.final_consensus_score != null ? (analytics.final_consensus_score * 100).toFixed(0) + '%' : '—' }}
          </div>
          <div class="panel-title stat-label">{{ t('analyticsPage.finalConsensus') }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ analytics.total_rounds ?? '—' }}</div>
          <div class="panel-title stat-label">{{ t('analyticsPage.rounds') }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ analytics.total_turns ?? '—' }}</div>
          <div class="panel-title stat-label">{{ t('analyticsPage.totalTurns') }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ analytics.session_duration ?? '—' }}</div>
          <div class="panel-title stat-label">{{ t('analyticsPage.duration') }}</div>
        </div>
      </div>

      <div v-if="consensusChartData" class="panel-box" style="margin-bottom: 24px;">
        <div class="panel-title">{{ t('analyticsPage.consensusTrajectory') }}</div>
        <div style="height: 200px;">
          <Line :data="consensusChartData" :options="chartOptions" />
        </div>
      </div>

      <div v-if="analytics.influence_leaderboard?.length" style="margin-bottom: 24px;">
        <div class="section-title">{{ t('analyticsPage.influenceLeaderboard') }}</div>
        <table class="data-table">
          <thead>
            <tr><th>{{ t('analyticsPage.agent') }}</th><th>{{ t('analyticsPage.combinedScore') }}</th><th>{{ t('analyticsPage.eigenvector') }}</th><th>{{ t('analyticsPage.betweenness') }}</th></tr>
          </thead>
          <tbody>
            <tr v-for="(a, i) in analytics.influence_leaderboard" :key="i">
              <td>{{ a.name }}</td>
              <td><strong>{{ a.combined_score?.toFixed(3) ?? '—' }}</strong></td>
              <td>{{ a.eigenvector?.toFixed(3) ?? '—' }}</td>
              <td>{{ a.betweenness?.toFixed(3) ?? '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="analytics.risk_table?.length" style="margin-bottom: 24px;">
        <div class="section-title">{{ t('analyticsPage.riskAssessment') }}</div>
        <table class="data-table">
          <thead>
            <tr><th>{{ t('analyticsPage.agent') }}</th><th>{{ t('analyticsPage.score') }}</th><th>{{ t('analyticsPage.level') }}</th><th>{{ t('analyticsPage.drivers') }}</th></tr>
          </thead>
          <tbody>
            <tr v-for="(r, i) in analytics.risk_table" :key="i">
              <td>{{ r.name }}</td>
              <td>{{ r.score?.toFixed(2) ?? '—' }}</td>
              <td><span :style="{ color: riskColor(r.level), fontWeight: 600 }">{{ r.level }}</span></td>
              <td style="color: var(--text-muted); font-size: 12px;">{{ (r.drivers || []).join(', ') }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="analytics.coalition_map?.length" style="margin-bottom: 24px;">
        <div class="section-title">{{ t('analyticsPage.finalCoalitionMap') }}</div>
        <div style="display: flex; flex-wrap: wrap; gap: 12px;">
          <div v-for="(g, i) in analytics.coalition_map" :key="i" class="panel-box" style="flex: 1; min-width: 200px;">
            <div class="panel-title" :style="{ color: g.color || 'var(--accent)' }">{{ g.label }}</div>
            <div v-for="m in g.members" :key="m" style="font-size: 13px; padding: 2px 0;">{{ m }}</div>
            <div v-if="g.similarity != null" style="font-size: 11px; color: var(--text-muted); margin-top: 6px;">
              {{ t('analyticsPage.intraSimilarity', { value: g.similarity.toFixed(3) }) }}
            </div>
          </div>
        </div>
      </div>

      <!-- Voting Matrix (issue #60) -->
      <div class="panel-box" style="margin-bottom: 24px;">
        <VotingMatrix :items="votingItems" />
      </div>

    </div>
  </div>
</template>

<style scoped>
.stat-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
  margin-bottom: 24px;
}

.stat-card {
  text-align: center;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--text);
}

.stat-label {
  margin: 4px 0 0;
}

@media (max-width: 600px) {
  .stat-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .stat-value {
    font-size: 22px;
  }
}

@media (max-width: 380px) {
  .stat-grid {
    grid-template-columns: 1fr;
  }
}
</style>
