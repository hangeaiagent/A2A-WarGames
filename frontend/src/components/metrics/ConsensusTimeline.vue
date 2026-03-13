<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTheme } from '../../composables/useTheme'
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

const { t } = useI18n()
const { theme } = useTheme()

const props = defineProps({ rounds: { type: Array, default: () => [] } })

function getCSSVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

// chartData and chartOptions reference theme.value so Vue re-evaluates them
// whenever the user switches between dark and light mode.
const chartData = computed(() => {
  // eslint-disable-next-line no-unused-expressions
  theme.value // track theme reactivity
  return {
    labels: props.rounds.map((_, i) => `R${i + 1}`),
    datasets: [{
      label: 'Consensus',
      data: props.rounds.map(r => r.consensus_score ?? r.score ?? 0),
      borderColor: getCSSVar('--accent') || '#e94560',
      backgroundColor: getCSSVar('--accent-glow') || 'rgba(233, 69, 96, 0.1)',
      tension: 0.35,
      fill: true,
      pointRadius: 4,
      pointHoverRadius: 8,
      pointBackgroundColor: getCSSVar('--accent') || '#e94560',
      pointBorderColor: getCSSVar('--surface') || '#1a1a2e',
      pointBorderWidth: 2,
      pointHoverBackgroundColor: getCSSVar('--accent') || '#e94560',
      pointHoverBorderColor: '#fff',
    }],
  }
})

const chartOptions = computed(() => {
  // eslint-disable-next-line no-unused-expressions
  theme.value // track theme reactivity
  const textMuted = getCSSVar('--text-muted') || '#999999'
  const border = getCSSVar('--border') || '#16213e'
  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: {
      duration: 600,
      easing: 'easeOutQuart',
    },
    transitions: {
      active: {
        animation: {
          duration: 300,
        },
      },
    },
    interaction: {
      intersect: false,
      mode: 'index',
    },
    scales: {
      y: { min: 0, max: 1, ticks: { color: textMuted }, grid: { color: border } },
      x: { ticks: { color: textMuted }, grid: { color: border } },
    },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: getCSSVar('--surface') || '#1a1a2e',
        titleColor: getCSSVar('--text') || '#e0e0e0',
        bodyColor: getCSSVar('--text-muted') || '#999',
        borderColor: getCSSVar('--border') || '#333',
        borderWidth: 1,
        cornerRadius: 6,
        padding: 8,
        displayColors: false,
        callbacks: {
          label: (ctx) => `Consensus: ${(ctx.parsed.y * 100).toFixed(0)}%`,
        },
      },
    },
  }
})
</script>

<template>
  <div v-if="rounds.length" class="panel-box ct-container">
    <div class="panel-title">{{ t('metrics.consensusTimeline', 'Consensus Timeline') }}</div>
    <div class="ct-chart">
      <Line :data="chartData" :options="chartOptions" />
    </div>
  </div>
</template>

<style scoped>
.ct-container {
  min-height: 160px;
}

.ct-chart {
  height: 160px;
}
</style>
