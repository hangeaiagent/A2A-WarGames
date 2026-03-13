<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import * as d3 from 'd3'

const props = defineProps({
  stakeholders: { type: Array, default: () => [] },
  edges:        { type: Array, default: () => [] },
})

const svgRef     = ref(null)
const wrapperRef = ref(null)
const tooltip    = ref({ visible: false, x: 0, y: 0, node: null })

let simulation  = null
let resizeObserver = null

// ── helpers ────────────────────────────────────────────────────────────────
function getTokenColor(varName, fallback) {
  return getComputedStyle(document.documentElement).getPropertyValue(varName).trim() || fallback
}

function edgeColor(type) {
  if (type === 'alliance' || type === 'alignment') return getTokenColor('--success', '#3fb950')
  if (type === 'tension')                           return getTokenColor('--danger', '#f85149')
  return getTokenColor('--border', '#30363d')
}

function edgeWidth(strength) {
  const s = Math.max(0, Math.min(1, strength ?? 0.5))
  return 1 + s * 3  // 1–4 px
}

function nodeRadius(influence) {
  const i = Math.max(0, Math.min(1, influence ?? 0.5))
  return 10 + i * 20  // 10–30 px
}

// ── main draw ──────────────────────────────────────────────────────────────
function draw() {
  if (!svgRef.value || !wrapperRef.value) return

  const width  = wrapperRef.value.clientWidth  || 600
  const height = Math.max(400, wrapperRef.value.clientHeight || 400)

  // Build slug → stakeholder map for linking edges
  const slugMap = {}
  props.stakeholders.forEach(s => { slugMap[s.slug] = s })

  // Clone nodes so D3 can mutate x/y without touching store refs
  const nodes = props.stakeholders.map(s => ({ ...s }))

  // Build links — edges reference by slug; D3 forceLink needs object refs
  const nodeBySlug = {}
  nodes.forEach(n => { nodeBySlug[n.slug] = n })

  const links = props.edges
    .filter(e => nodeBySlug[e.source] && nodeBySlug[e.target])
    .map(e => ({
      ...e,
      source: nodeBySlug[e.source],
      target: nodeBySlug[e.target],
    }))

  // Clear previous render
  d3.select(svgRef.value).selectAll('*').remove()

  const svg = d3.select(svgRef.value)
    .attr('width',  width)
    .attr('height', height)

  // Arrow markers per edge type
  const defs = svg.append('defs')
  ;['alliance', 'tension', 'neutral'].forEach(type => {
    defs.append('marker')
      .attr('id', `arrow-${type}`)
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 10)
      .attr('refY', 0)
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M0,-5L10,0L0,5')
      .attr('fill', edgeColor(type))
  })

  // Root group for zoom/pan
  const g = svg.append('g')

  svg.call(
    d3.zoom()
      .scaleExtent([0.3, 4])
      .on('zoom', (event) => g.attr('transform', event.transform))
  )

  // Stop any previous simulation
  if (simulation) simulation.stop()

  simulation = d3.forceSimulation(nodes)
    .force('link',   d3.forceLink(links).id(d => d.id).distance(120).strength(0.5))
    .force('charge', d3.forceManyBody().strength(-300))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collision', d3.forceCollide().radius(d => nodeRadius(d.influence) + 8))

  // ── edges ──
  const linkGroup = g.append('g').attr('class', 'links')

  const link = linkGroup.selectAll('line')
    .data(links)
    .join('line')
    .attr('stroke', d => edgeColor(d.type))
    .attr('stroke-width', d => edgeWidth(d.strength))
    .attr('stroke-opacity', 0.8)
    .attr('marker-end', d => {
      const t = d.type === 'alliance' || d.type === 'alignment' ? 'alliance'
              : d.type === 'tension' ? 'tension' : 'neutral'
      return `url(#arrow-${t})`
    })

  // ── edge labels ──
  const edgeLabel = g.append('g').attr('class', 'edge-labels')
    .selectAll('text')
    .data(links.filter(d => d.label))
    .join('text')
    .attr('text-anchor', 'middle')
    .attr('fill', '#888')
    .attr('font-size', 10)
    .attr('pointer-events', 'none')
    .text(d => d.label)

  // ── nodes ──
  const nodeGroup = g.append('g').attr('class', 'nodes')

  const nodeG = nodeGroup.selectAll('g')
    .data(nodes)
    .join('g')
    .attr('class', 'node')
    .style('cursor', 'grab')
    .call(
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
          d.fx = null
          d.fy = null
        })
    )
    .on('mouseenter', (event, d) => {
      tooltip.value = {
        visible: true,
        x: event.clientX + 12,
        y: event.clientY - 10,
        node: d,
      }
    })
    .on('mousemove', (event) => {
      tooltip.value.x = event.clientX + 12
      tooltip.value.y = event.clientY - 10
    })
    .on('mouseleave', () => {
      tooltip.value.visible = false
    })

  // Circle
  nodeG.append('circle')
    .attr('r', d => nodeRadius(d.influence))
    .attr('fill', d => d.color || '#58a6ff')
    .attr('fill-opacity', 0.85)
    .attr('stroke', '#ffffff22')
    .attr('stroke-width', 1.5)

  // Label — use CSS variable for theme-aware color
  const textColor = getComputedStyle(document.documentElement).getPropertyValue('--text').trim() || '#e0e0e0'
  nodeG.append('text')
    .attr('text-anchor', 'middle')
    .attr('dy', d => nodeRadius(d.influence) + 14)
    .attr('fill', textColor)
    .attr('font-size', 11)
    .attr('font-family', 'inherit')
    .attr('pointer-events', 'none')
    .text(d => d.name)

  // ── tick ──
  simulation.on('tick', () => {
    link
      .attr('x1', d => d.source.x)
      .attr('y1', d => d.source.y)
      .attr('x2', d => {
        const r = nodeRadius(d.target.influence) + 6
        const dx = d.target.x - d.source.x
        const dy = d.target.y - d.source.y
        const dist = Math.sqrt(dx * dx + dy * dy) || 1
        return d.target.x - (dx / dist) * r
      })
      .attr('y2', d => {
        const r = nodeRadius(d.target.influence) + 6
        const dx = d.target.x - d.source.x
        const dy = d.target.y - d.source.y
        const dist = Math.sqrt(dx * dx + dy * dy) || 1
        return d.target.y - (dy / dist) * r
      })

    edgeLabel
      .attr('x', d => (d.source.x + d.target.x) / 2)
      .attr('y', d => (d.source.y + d.target.y) / 2)

    nodeG.attr('transform', d => `translate(${d.x},${d.y})`)
  })
}

// ── legend data ─────────────────────────────────────────────────────────────
// Colors are read at render time from CSS variables so they stay reactive to theme changes.
const legendItems = [
  { label: 'Alliance / Alignment', varName: '--success', fallback: '#3fb950' },
  { label: 'Tension',              varName: '--danger',  fallback: '#f85149' },
  { label: 'Neutral',              varName: '--border',  fallback: '#888888' },
]

// ── lifecycle ──────────────────────────────────────────────────────────────
onMounted(() => {
  draw()

  resizeObserver = new ResizeObserver(() => { draw() })
  if (wrapperRef.value) resizeObserver.observe(wrapperRef.value)
})

onBeforeUnmount(() => {
  if (simulation) simulation.stop()
  if (resizeObserver) resizeObserver.disconnect()
})

watch(() => [props.stakeholders, props.edges], () => { draw() }, { deep: true })
</script>

<template>
  <div class="graph-wrapper" ref="wrapperRef">
    <svg ref="svgRef" class="graph-svg" />

    <!-- Tooltip -->
    <div
      v-if="tooltip.visible && tooltip.node"
      class="graph-tooltip"
      :style="{ left: tooltip.x + 'px', top: tooltip.y + 'px' }"
    >
      <div class="tip-name">{{ tooltip.node.name }}</div>
      <div class="tip-row"><span>Role</span> {{ tooltip.node.role || '—' }}</div>
      <div class="tip-row"><span>Influence</span> {{ Math.round((tooltip.node.influence || 0) * 100) }}%</div>
      <div class="tip-row"><span>Attitude</span> {{ tooltip.node.attitude_label || tooltip.node.attitude || '—' }}</div>
    </div>

    <!-- Legend -->
    <div class="graph-legend">
      <div v-for="item in legendItems" :key="item.label" class="legend-item">
        <span class="legend-line" :style="{ background: getTokenColor(item.varName, item.fallback) }" />
        {{ item.label }}
      </div>
      <div class="legend-item">
        <span class="legend-circle" />
        Node size = Influence
      </div>
    </div>

    <!-- Empty state -->
    <div v-if="stakeholders.length === 0" class="graph-empty">
      No stakeholders to display.
    </div>
  </div>
</template>

<style scoped>
.graph-wrapper {
  position: relative;
  width: 100%;
  min-height: 400px;
  background: var(--surface);
  border-radius: var(--radius);
  border: 1px solid var(--border);
  overflow: hidden;
}

.graph-svg {
  display: block;
  width: 100%;
  min-height: 400px;
}

/* Tooltip */
.graph-tooltip {
  position: fixed;
  z-index: 9999;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 10px 14px;
  pointer-events: none;
  font-size: 12px;
  color: var(--text);
  min-width: 160px;
  box-shadow: var(--shadow-lg);
}

.tip-name {
  font-weight: 600;
  font-size: 13px;
  margin-bottom: 6px;
  color: var(--text);
}

.tip-row {
  display: flex;
  gap: 6px;
  margin-bottom: 3px;
  color: var(--text-muted);
}

.tip-row span {
  color: var(--text-muted);
  min-width: 68px;
}

/* Legend */
.graph-legend {
  position: absolute;
  bottom: 12px;
  left: 12px;
  display: flex;
  flex-direction: column;
  gap: 5px;
  font-size: 11px;
  color: var(--text-muted);
  background: color-mix(in srgb, var(--surface) 85%, transparent);
  padding: 8px 10px;
  border-radius: var(--radius);
  border: 1px solid var(--border);
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 7px;
}

.legend-line {
  display: inline-block;
  width: 22px;
  height: 2px;
  border-radius: 1px;
  flex-shrink: 0;
}

.legend-circle {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #58a6ff;
  flex-shrink: 0;
}

/* Empty state */
.graph-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted, #888);
  font-size: 14px;
}
</style>
