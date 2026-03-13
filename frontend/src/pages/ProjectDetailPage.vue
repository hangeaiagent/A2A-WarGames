<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useProjectStore } from '../stores/projects'
import StakeholderGraph from '../components/StakeholderGraph.vue'

const route = useRoute()
const store = useProjectStore()
const { t } = useI18n()

const projectId = computed(() => Number(route.params.projectId))
const activeTab  = ref('graph')   // 'graph' | 'list'
const loading    = ref(false)

async function loadData(id) {
  if (!id) return
  loading.value = true
  try {
    await Promise.all([
      store.fetchProject(id),
      store.fetchStakeholders(id),
      store.fetchEdges(id),
    ])
  } finally {
    loading.value = false
  }
}

onMounted(() => loadData(projectId.value))
watch(projectId, id => loadData(id))
</script>

<template>
  <div>
    <!-- Header -->
    <div class="page-header">
      <div>
        <div class="page-title">
          {{ store.currentProject?.name || t('projectDetail.title') }}
          <span v-if="store.currentProject?.organization" style="color: var(--text-muted); font-size: 16px; font-weight: 400;">
            — {{ store.currentProject.organization }}
          </span>
        </div>
        <div class="page-subtitle">
          {{ store.stakeholders.length }} {{ t('projectDetail.stakeholders') }} · {{ store.edges.length }} {{ t('projectDetail.relationships') }}
        </div>
      </div>
    </div>

    <!-- Tab bar -->
    <div class="tab-bar">
      <button
        class="tab-btn"
        :class="{ active: activeTab === 'graph' }"
        @click="activeTab = 'graph'"
      >
        {{ t('projectDetail.stakeholderNetwork') }}
      </button>
      <button
        class="tab-btn"
        :class="{ active: activeTab === 'list' }"
        @click="activeTab = 'list'"
      >
        {{ t('projectDetail.stakeholderList') }}
      </button>
    </div>

    <!-- Loading -->
    <div v-if="loading" style="text-align: center; padding: 48px; color: var(--text-muted);">
      {{ t('projectDetail.loading') }}
    </div>

    <template v-else>
      <!-- Stakeholder Network Graph -->
      <div v-show="activeTab === 'graph'" class="section">
        <StakeholderGraph
          :stakeholders="store.stakeholders"
          :edges="store.edges"
        />
      </div>

      <!-- Stakeholder list (compact) -->
      <div v-show="activeTab === 'list'" class="section">
        <div v-if="store.stakeholders.length === 0" class="empty-state">
          <p>{{ t('projectDetail.noStakeholders') }}</p>
        </div>
        <table v-else class="data-table">
          <thead>
            <tr>
              <th>{{ t('projectDetail.name') }}</th>
              <th>{{ t('projectDetail.role') }}</th>
              <th>{{ t('projectDetail.attitude') }}</th>
              <th>{{ t('projectDetail.influence') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in store.stakeholders" :key="s.id">
              <td>
                <span
                  class="influence-dot"
                  :style="{ background: s.color }"
                />
                <strong>{{ s.name }}</strong>
              </td>
              <td style="color: var(--text-muted);">{{ s.role }}</td>
              <td>
                <span :class="['card-badge', `att-${s.attitude}`]">
                  {{ s.attitude_label || s.attitude }}
                </span>
              </td>
              <td>{{ Math.round((s.influence || 0) * 100) }}%</td>
            </tr>
          </tbody>
        </table>

        <!-- Edges (relationships) -->
        <div v-if="store.edges.length > 0" style="margin-top: 24px;">
          <div class="section-title">{{ t('projectDetail.relationshipsTitle') }}</div>
          <table class="data-table">
            <thead>
              <tr>
                <th>{{ t('projectDetail.source') }}</th>
                <th>{{ t('projectDetail.type') }}</th>
                <th>{{ t('projectDetail.target') }}</th>
                <th>{{ t('projectDetail.strength') }}</th>
                <th>{{ t('projectDetail.label') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="e in store.edges" :key="e.id">
                <td>{{ e.source }}</td>
                <td>
                  <span
                    class="edge-badge"
                    :style="{
                      color: e.type === 'alignment' || e.type === 'alliance'
                        ? '#3fb950'
                        : e.type === 'tension'
                          ? '#f85149'
                          : '#888',
                    }"
                  >
                    {{ e.type }}
                  </span>
                </td>
                <td>{{ e.target }}</td>
                <td>{{ Math.round((e.strength || 0) * 100) }}%</td>
                <td style="color: var(--text-muted); font-size: 12px;">{{ e.label }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.tab-bar {
  display: flex;
  gap: 4px;
  margin-bottom: 20px;
  border-bottom: 1px solid var(--border);
  padding-bottom: 0;
}

.tab-btn {
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  padding: 8px 18px;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: color 0.15s, border-color 0.15s;
  margin-bottom: -1px;
}

.tab-btn:hover {
  color: var(--text);
}

.tab-btn.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}

.section {
  margin-top: 4px;
}

.edge-badge {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
</style>
