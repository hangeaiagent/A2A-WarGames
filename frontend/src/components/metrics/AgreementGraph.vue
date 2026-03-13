<script setup>
import { ref, onMounted, onBeforeUnmount, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import * as d3 from 'd3'

const { t } = useI18n()

const props = defineProps({
  /** Array of { slug, name, color? } */
  agents: { type: Array, default: () => [] },
  /**
   * Observer data keyed by speaker slug:
   * { [slug]: { behavioral_signals: { agreement_with: [], disagreement_with: [] }, ... } }
   */
  observerData: { type: Object, default: () => ({}) },
  /** Currently selected/hovered agent slug (optional) */
  highlightAgent: { type: String, default: null },
})

const emit = defineEmits(['select-agent'])

const svgRef = ref(null)
const wrapperRef = ref(null)
const tooltip = ref({ visible: false, x: 0, y: 0, data: null })
const selectedAgent = ref(null)

let simulation = null
let resizeObserver = null

// Persistent D3 selections for incremental updates
let svgSel = null
let gSel = null
let linkSel = null
let edgeLabelSel = null
let nodeGSel = null

// Persistent node position map — preserves positions across data updates
const nodePositions = {}

// ── Constants ──────────────────────────────────────────────────────────────
const MIN_EDGE_WIDTH = 1
const EDGE_WIDTH_SCALE = 1.5
const MAX_EDGE_WIDTH = 6
const DEFAULT_OPACITY = 0.85
const DIMMED_OPACITY = 0.3
const NODE_RADIUS = 16

// ── Resolve CSS variables at draw time for theme correctness ───────────────
function resolveColor(varName) {
  return getComputedStyle(document.documentElement).getPropertyValue(varName).trim()
}

// ── Compute edges from observer data ────────────────────────────────────────
const graphEdges = computed(() => {
  const edgeMap = {}

  for (const [speaker, obs] of Object.entries(props.observerData)) {
    const signals = obs?.behavioral_signals || obs || {}
    const agreements = signals.agreement_with || []
    const disagreements = signals.disagreement_with || []

    for (const target of agreements) {
      const targetSlug = slugify(target)
      const key = `${speaker}→${targetSlug}`
      if (!edgeMap[key]) edgeMap[key] = { source: speaker, target: targetSlug, agree: 0, disagree: 0 }
      edgeMap[key].agree++
    }

    for (const target of disagreements) {
      const targetSlug = slugify(target)
      const key = `${speaker}→${targetSlug}`
      if (!edgeMap[key]) edgeMap[key] = { source: speaker, target: targetSlug, agree: 0, disagree: 0 }
      edgeMap[key].disagree++
    }
  }

  return Object.values(edgeMap)
})

// Slugify helper — matches names to slugs for observer data that uses display names
function slugify(name) {
  const agentSlugs = props.agents.map(a => a.slug)
  if (agentSlugs.includes(name)) return name

  const agent = props.agents.find(a =>
    a.name?.toLowerCase() === name?.toLowerCase() ||
    a.slug?.toLowerCase() === name?.toLowerCase?.()
  )
  if (agent) return agent.slug

  return (name || '').toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '')
}

// ── Color helpers (resolve from CSS variables) ─────────────────────────────
function edgeColor(edge) {
  if (edge.agree > 0 && edge.disagree === 0) return resolveColor('--success')
  if (edge.disagree > 0 && edge.agree === 0) return resolveColor('--danger')
  return resolveColor('--warn')
}

function edgeWidth(edge) {
  const total = edge.agree + edge.disagree
  return Math.min(MIN_EDGE_WIDTH + total * EDGE_WIDTH_SCALE, MAX_EDGE_WIDTH)
}

function edgeLabel(edge) {
  const parts = []
  if (edge.agree > 0) parts.push(`+${edge.agree}`)
  if (edge.disagree > 0) parts.push(`-${edge.disagree}`)
  return parts.join(' / ')
}

function markerType(edge) {
  if (edge.agree > 0 && edge.disagree === 0) return 'agree'
  if (edge.disagree > 0 && edge.agree === 0) return 'disagree'
  return 'mixed'
}

// ── Initial draw — creates SVG structure and simulation ────────────────────
function initDraw() {
  if (!svgRef.value || !wrapperRef.value) return
  if (!props.agents.length) return

  const width = wrapperRef.value.clientWidth || 400
  const height = Math.max(180, wrapperRef.value.clientHeight || 180)

  // Clear previous
  d3.select(svgRef.value).selectAll('*').remove()
  if (simulation) simulation.stop()

  svgSel = d3.select(svgRef.value)
    .attr('width', width)
    .attr('height', height)

  // Arrow markers — resolve colors from CSS vars
  const defs = svgSel.append('defs')
  const successColor = resolveColor('--success')
  const dangerColor = resolveColor('--danger')
  const warnColor = resolveColor('--warn')
  ;[
    { type: 'agree', color: successColor },
    { type: 'disagree', color: dangerColor },
    { type: 'mixed', color: warnColor },
  ].forEach(({ type, color }) => {
    defs.append('marker')
      .attr('id', `dag-arrow-${type}`)
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 10)
      .attr('refY', 0)
      .attr('markerWidth', 5)
      .attr('markerHeight', 5)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M0,-5L10,0L0,5')
      .attr('fill', color)
  })

  gSel = svgSel.append('g')

  svgSel.call(
    d3.zoom()
      .scaleExtent([0.5, 3])
      .on('zoom', (event) => gSel.attr('transform', event.transform))
  )

  // Create persistent group layers
  gSel.append('g').attr('class', 'dag-links')
  gSel.append('g').attr('class', 'dag-edge-labels')
  gSel.append('g').attr('class', 'dag-nodes')

  // Build initial data and simulation
  rebuildSimulation(width, height)
}

// ── Rebuild simulation with current data ───────────────────────────────────
function rebuildSimulation(width, height) {
  if (!gSel) return

  if (!width || !height) {
    width = wrapperRef.value?.clientWidth || 400
    height = Math.max(180, wrapperRef.value?.clientHeight || 180)
  }

  const agentSlugs = new Set(props.agents.map(a => a.slug))

  // Clone nodes, restoring persisted positions
  const nodes = props.agents.map(a => {
    const pos = nodePositions[a.slug]
    return {
      ...a,
      id: a.slug,
      x: pos?.x ?? (width / 2 + (Math.random() - 0.5) * 60),
      y: pos?.y ?? (height / 2 + (Math.random() - 0.5) * 60),
      fx: pos?.fx ?? null,
      fy: pos?.fy ?? null,
    }
  })

  const nodeBySlug = {}
  nodes.forEach(n => { nodeBySlug[n.slug] = n })

  // Build links, filtering to valid agents only
  const links = graphEdges.value
    .filter(e => nodeBySlug[e.source] && agentSlugs.has(e.target) && nodeBySlug[e.target])
    .map(e => ({
      ...e,
      source: nodeBySlug[e.source],
      target: nodeBySlug[e.target],
    }))

  if (simulation) simulation.stop()

  simulation = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(links).id(d => d.id).distance(90).strength(0.4))
    .force('charge', d3.forceManyBody().strength(-200))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collision', d3.forceCollide().radius(NODE_RADIUS + 12))

  // ── Update edges with data join ──
  linkSel = gSel.select('.dag-links')
    .selectAll('line')
    .data(links, d => `${d.source.slug ?? d.source}→${d.target.slug ?? d.target}`)
    .join(
      enter => enter.append('line').attr('stroke-opacity', 0).call(el => el.transition().duration(300).attr('stroke-opacity', 0.7)),
      update => update,
      exit => exit.transition().duration(200).attr('stroke-opacity', 0).remove()
    )
    .attr('stroke', d => edgeColor(d))
    .attr('stroke-width', d => edgeWidth(d))
    .attr('marker-end', d => `url(#dag-arrow-${markerType(d)})`)

  // ── Update edge labels with data join ──
  edgeLabelSel = gSel.select('.dag-edge-labels')
    .selectAll('text')
    .data(links, d => `${d.source.slug ?? d.source}→${d.target.slug ?? d.target}`)
    .join('text')
    .attr('text-anchor', 'middle')
    .attr('fill', resolveColor('--text-muted'))
    .attr('font-size', 9)
    .attr('pointer-events', 'none')
    .text(d => edgeLabel(d))

  // ── Update nodes with data join ──
  const textColor = resolveColor('--text')

  nodeGSel = gSel.select('.dag-nodes')
    .selectAll('g.dag-node')
    .data(nodes, d => d.slug)
    .join(
      enter => {
        const g = enter.append('g').attr('class', 'dag-node').style('cursor', 'pointer')
        g.append('circle')
          .attr('r', NODE_RADIUS)
          .attr('fill-opacity', DEFAULT_OPACITY)
          .attr('stroke', '#ffffff22')
          .attr('stroke-width', 1.5)
        g.append('text')
          .attr('text-anchor', 'middle')
          .attr('dy', 28)
          .attr('fill', textColor)
          .attr('font-size', 10)
          .attr('font-family', 'inherit')
          .attr('pointer-events', 'none')
        return g
      },
      update => update,
      exit => exit.transition().duration(200).style('opacity', 0).remove()
    )

  // Update circle attributes
  nodeGSel.select('circle')
    .attr('fill', d => d.color || resolveColor('--info'))
    .attr('fill-opacity', d => {
      if (selectedAgent.value && selectedAgent.value !== d.slug) return DIMMED_OPACITY
      return DEFAULT_OPACITY
    })
    .attr('stroke', d => {
      if (selectedAgent.value === d.slug || props.highlightAgent === d.slug) return '#fff'
      return '#ffffff22'
    })
    .attr('stroke-width', d => (selectedAgent.value === d.slug || props.highlightAgent === d.slug) ? 2.5 : 1.5)

  // Update text labels
  nodeGSel.select('text')
    .attr('fill', textColor)
    .text(d => d.name?.length > 12 ? d.name.slice(0, 11) + '…' : d.name)

  // Drag — pin nodes at dropped position, double-click to release
  nodeGSel.call(
    d3.drag()
      .on('start', (event, d) => {
        if (!event.active) simulation.alphaTarget(0.3).restart()
        d.fx = d.x
        d.fy = d.y
      })
      .on('drag', (event, d) => {
        d.fx = event.x
        d.fy = event.y
      })
      .on('end', (event, d) => {
        if (!event.active) simulation.alphaTarget(0)
        // Pin node at dropped position
        d.fx = d.x
        d.fy = d.y
        nodePositions[d.slug] = { x: d.x, y: d.y, fx: d.fx, fy: d.fy }
      })
  )

  // Double-click to release pinned node
  nodeGSel.on('dblclick', (event, d) => {
    event.stopPropagation()
    d.fx = null
    d.fy = null
    if (nodePositions[d.slug]) {
      delete nodePositions[d.slug].fx
      delete nodePositions[d.slug].fy
    }
    simulation.alpha(0.3).restart()
  })

  // Hover tooltip
  nodeGSel
    .on('mouseenter', (event, d) => {
      const agreeCount = graphEdges.value.filter(e => e.source === d.slug).reduce((s, e) => s + e.agree, 0)
      const disagreeCount = graphEdges.value.filter(e => e.source === d.slug).reduce((s, e) => s + e.disagree, 0)
      tooltip.value = {
        visible: true,
        x: event.clientX + 12,
        y: event.clientY - 10,
        data: { name: d.name, slug: d.slug, agreeCount, disagreeCount },
      }
    })
    .on('mousemove', (event) => {
      tooltip.value.x = event.clientX + 12
      tooltip.value.y = event.clientY - 10
    })
    .on('mouseleave', () => { tooltip.value.visible = false })
    .on('click', (_event, d) => {
      selectedAgent.value = selectedAgent.value === d.slug ? null : d.slug
      emit('select-agent', selectedAgent.value)
    })

  // ── tick ──
  simulation.on('tick', () => {
    linkSel
      .attr('x1', d => d.source.x)
      .attr('y1', d => d.source.y)
      .attr('x2', d => {
        const dx = d.target.x - d.source.x
        const dy = d.target.y - d.source.y
        const dist = Math.sqrt(dx * dx + dy * dy) || 1
        return d.target.x - (dx / dist) * (NODE_RADIUS + 6)
      })
      .attr('y2', d => {
        const dx = d.target.x - d.source.x
        const dy = d.target.y - d.source.y
        const dist = Math.sqrt(dx * dx + dy * dy) || 1
        return d.target.y - (dy / dist) * (NODE_RADIUS + 6)
      })

    edgeLabelSel
      .attr('x', d => (d.source.x + d.target.x) / 2)
      .attr('y', d => (d.source.y + d.target.y) / 2 - 4)

    nodeGSel.attr('transform', d => `translate(${d.x},${d.y})`)

    // Persist positions for incremental updates
    nodes.forEach(n => {
      nodePositions[n.slug] = { x: n.x, y: n.y, fx: n.fx, fy: n.fy }
    })
  })

  // Gentle restart for incremental updates
  simulation.alpha(0.3).restart()
}

// ── Incremental update — only update edges/styles without rebuilding ──────
function incrementalUpdate() {
  if (!gSel || !simulation) {
    initDraw()
    return
  }
  rebuildSimulation()
}

// ── Legend (computed for i18n reactivity) ───────────────────────────────────
const legendItems = computed(() => [
  { labelKey: 'agreementGraph.legendAgree', color: resolveColor('--success') },
  { labelKey: 'agreementGraph.legendDisagree', color: resolveColor('--danger') },
  { labelKey: 'agreementGraph.legendMixed', color: resolveColor('--warn') },
])

// ── Lifecycle ──────────────────────────────────────────────────────────────
onMounted(() => {
  initDraw()
  resizeObserver = new ResizeObserver(() => initDraw())
  if (wrapperRef.value) resizeObserver.observe(wrapperRef.value)
})

onBeforeUnmount(() => {
  if (simulation) simulation.stop()
  if (resizeObserver) resizeObserver.disconnect()
})

// Full redraw only when agent list changes; incremental for observer data
watch(() => props.agents, () => initDraw(), { deep: true })
watch(() => props.observerData, () => incrementalUpdate(), { deep: true })
watch(() => props.highlightAgent, () => incrementalUpdate())
</script>

<template>
  <div class="dag-wrapper" ref="wrapperRef">
    <svg ref="svgRef" class="dag-svg" />

    <!-- Tooltip -->
    <div
      v-if="tooltip.visible && tooltip.data"
      class="dag-tooltip"
      :style="{ left: tooltip.x + 'px', top: tooltip.y + 'px' }"
    >
      <div class="dag-tip-name">{{ tooltip.data.name }}</div>
      <div class="dag-tip-row">
        <span class="dag-tip-label">{{ t('agreementGraph.tooltipAgreements') }}:</span>
        <span class="dag-tip-val agree">{{ tooltip.data.agreeCount }}</span>
      </div>
      <div class="dag-tip-row">
        <span class="dag-tip-label">{{ t('agreementGraph.tooltipDisagreements') }}:</span>
        <span class="dag-tip-val disagree">{{ tooltip.data.disagreeCount }}</span>
      </div>
    </div>

    <!-- Legend -->
    <div class="dag-legend">
      <div v-for="item in legendItems" :key="item.labelKey" class="dag-legend-item">
        <span class="dag-legend-line" :style="{ background: item.color }" />
        {{ t(item.labelKey) }}
      </div>
      <div class="dag-legend-item">
        <span class="dag-legend-line" :style="{ background: 'var(--text-muted)', height: '4px' }" />
        {{ t('agreementGraph.legendThickness') }}
      </div>
    </div>

    <!-- Empty state -->
    <div v-if="!agents.length || !Object.keys(observerData).length" class="dag-empty">
      {{ t('agreementGraph.empty') }}
    </div>
  </div>
</template>

<style scoped>
.dag-wrapper {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 180px;
  background: var(--surface);
  border-radius: var(--radius);
  overflow: hidden;
}

.dag-svg {
  display: block;
  width: 100%;
  height: 100%;
  min-height: 180px;
}

.dag-tooltip {
  position: fixed;
  z-index: 9999;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 8px 12px;
  pointer-events: none;
  font-size: 11px;
  color: var(--text);
  min-width: 140px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.5);
}

.dag-tip-name {
  font-weight: 600;
  font-size: 12px;
  margin-bottom: 4px;
}

.dag-tip-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 2px;
}

.dag-tip-label {
  color: var(--text-muted);
}

.dag-tip-val.agree { color: var(--success); font-weight: 600; }
.dag-tip-val.disagree { color: var(--danger); font-weight: 600; }

.dag-legend {
  position: absolute;
  bottom: 6px;
  left: 6px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  font-size: 10px;
  color: var(--text-muted);
  background: var(--surface-alt);
  padding: 6px 8px;
  border-radius: var(--radius);
  opacity: 0.9;
}

.dag-legend-item {
  display: flex;
  align-items: center;
  gap: 5px;
}

.dag-legend-line {
  display: inline-block;
  width: 16px;
  height: 2px;
  border-radius: 1px;
  flex-shrink: 0;
}

.dag-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  font-size: 12px;
  font-style: italic;
}
</style>
