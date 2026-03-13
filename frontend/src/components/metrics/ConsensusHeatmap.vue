<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps({
  /** Array of { slug, name } */
  agents: { type: Array, default: () => [] },
  /**
   * Observer data keyed by speaker slug:
   * { [slug]: { behavioral_signals: { agreement_with: [], disagreement_with: [] } } }
   */
  observerData: { type: Object, default: () => ({}) },
})

// ── Color constants for heatmap cells ──
const BASE_OPACITY = 0.2
const OPACITY_STEP = 0.15
const MAX_OPACITY = 0.85
const MIXED_OPACITY_STEP = 0.1
const MIXED_MAX_OPACITY = 0.6

// ── Resolve CSS variables for theme-aware colors ──
function resolveColorRGB(varName) {
  const hex = getComputedStyle(document.documentElement).getPropertyValue(varName).trim()
  return hexToRGB(hex)
}

function hexToRGB(hex) {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex)
  if (!result) return { r: 128, g: 128, b: 128 }
  return { r: parseInt(result[1], 16), g: parseInt(result[2], 16), b: parseInt(result[3], 16) }
}

// Build pairwise matrix: for each (speaker, target) compute net agreement score
const matrix = computed(() => {
  const slugs = props.agents.map(a => a.slug)
  const data = {}

  for (const s of slugs) {
    data[s] = {}
    for (const t of slugs) {
      data[s][t] = { agree: 0, disagree: 0 }
    }
  }

  for (const [speaker, obs] of Object.entries(props.observerData)) {
    if (!data[speaker]) continue
    const signals = obs?.behavioral_signals || obs || {}
    const agreements = signals.agreement_with || []
    const disagreements = signals.disagreement_with || []

    for (const target of agreements) {
      const slug = resolveSlug(target)
      if (slug && data[speaker][slug]) {
        data[speaker][slug].agree++
      }
    }

    for (const target of disagreements) {
      const slug = resolveSlug(target)
      if (slug && data[speaker][slug]) {
        data[speaker][slug].disagree++
      }
    }
  }

  return data
})

function resolveSlug(name) {
  const agent = props.agents.find(a =>
    a.slug === name ||
    a.name?.toLowerCase() === name?.toLowerCase()
  )
  return agent?.slug || null
}

// Compute cell color using CSS variable-derived RGB values
function cellColor(row, col) {
  if (row === col) return 'var(--surface-alt)'
  const cell = matrix.value[row]?.[col]
  if (!cell) return 'transparent'
  const net = cell.agree - cell.disagree
  const total = cell.agree + cell.disagree
  if (total === 0) return 'transparent'

  let rgb
  let opacity
  if (net > 0) {
    rgb = resolveColorRGB('--success')
    opacity = Math.min(BASE_OPACITY + total * OPACITY_STEP, MAX_OPACITY)
  } else if (net < 0) {
    rgb = resolveColorRGB('--danger')
    opacity = Math.min(BASE_OPACITY + total * OPACITY_STEP, MAX_OPACITY)
  } else {
    rgb = resolveColorRGB('--warn')
    opacity = Math.min(BASE_OPACITY + total * MIXED_OPACITY_STEP, MIXED_MAX_OPACITY)
  }
  return `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${opacity})`
}

function cellText(row, col) {
  if (row === col) return '—'
  const cell = matrix.value[row]?.[col]
  if (!cell) return ''
  const total = cell.agree + cell.disagree
  if (total === 0) return ''
  const net = cell.agree - cell.disagree
  return net > 0 ? `+${net}` : net < 0 ? `${net}` : '±0'
}

function cellTitle(row, col) {
  if (row === col) return t('agreementGraph.self')
  const cell = matrix.value[row]?.[col]
  if (!cell) return ''
  const rName = props.agents.find(a => a.slug === row)?.name || row
  const cName = props.agents.find(a => a.slug === col)?.name || col
  return `${rName} → ${cName}: ${cell.agree} ${t('agreementGraph.tooltipAgreements').toLowerCase()}, ${cell.disagree} ${t('agreementGraph.tooltipDisagreements').toLowerCase()}`
}

const hasData = computed(() => Object.keys(props.observerData).length > 0)
</script>

<template>
  <div class="heatmap-wrapper">
    <div v-if="agents.length && hasData" class="heatmap-scroll">
      <table class="heatmap-table">
        <thead>
          <tr>
            <th class="heatmap-corner"></th>
            <th
              v-for="col in agents"
              :key="col.slug"
              class="heatmap-col-header"
              :title="col.name"
            >
              {{ col.name?.length > 8 ? col.name.slice(0, 7) + '…' : col.name }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in agents" :key="row.slug">
            <td class="heatmap-row-header" :title="row.name">
              {{ row.name?.length > 8 ? row.name.slice(0, 7) + '…' : row.name }}
            </td>
            <td
              v-for="col in agents"
              :key="col.slug"
              class="heatmap-cell"
              :style="{ background: cellColor(row.slug, col.slug) }"
              :title="cellTitle(row.slug, col.slug)"
            >
              {{ cellText(row.slug, col.slug) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else class="heatmap-empty">
      {{ t('agreementGraph.empty') }}
    </div>
  </div>
</template>

<style scoped>
.heatmap-wrapper {
  width: 100%;
  height: 100%;
  min-height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.heatmap-scroll {
  overflow: auto;
  max-width: 100%;
  max-height: 100%;
}

.heatmap-table {
  border-collapse: collapse;
  font-size: 10px;
  white-space: nowrap;
}

.heatmap-corner {
  width: 60px;
}

.heatmap-col-header {
  padding: 3px 6px;
  text-align: center;
  color: var(--text-muted);
  font-weight: 500;
  font-size: 9px;
  max-width: 60px;
  overflow: hidden;
  text-overflow: ellipsis;
  writing-mode: vertical-lr;
  transform: rotate(180deg);
  height: 56px;
}

.heatmap-row-header {
  padding: 3px 6px;
  text-align: right;
  color: var(--text-muted);
  font-weight: 500;
  font-size: 9px;
  max-width: 60px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.heatmap-cell {
  width: 32px;
  height: 24px;
  text-align: center;
  font-size: 9px;
  font-weight: 600;
  color: var(--text);
  border: 1px solid var(--border);
  cursor: default;
  transition: background 200ms ease;
}

.heatmap-empty {
  color: var(--text-muted);
  font-size: 12px;
  font-style: italic;
}
</style>
