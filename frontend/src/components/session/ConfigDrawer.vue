<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const props = defineProps({
  modelValue: Object,
  featureFlags: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['update:modelValue', 'close'])

const drawerPanel = ref(null)

function update(key, val) {
  emit('update:modelValue', { ...props.modelValue, [key]: val })
}

function handleKeydown(e) {
  if (e.key === 'Escape') emit('close')
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
  document.body.style.overflow = 'hidden'
  drawerPanel.value?.focus()
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
  document.body.style.overflow = ''
})
</script>

<template>
  <div class="drawer-overlay" @click.self="emit('close')">
    <div
      ref="drawerPanel"
      class="drawer-panel"
      role="dialog"
      aria-modal="true"
      aria-labelledby="drawer-title"
      tabindex="-1"
    >
      <div class="drawer-header">
        <span id="drawer-title" class="page-title drawer-title">{{ t('configDrawer.title') }}</span>
        <button class="drawer-close-btn" @click="emit('close')">✕</button>
      </div>

      <div class="form-group">
        <label class="form-label">{{ t('configDrawer.numRounds') }}</label>
        <input type="number" min="1" max="10" class="form-input"
          :value="modelValue.num_rounds ?? 5"
          @input="update('num_rounds', parseInt($event.target.value))" />
      </div>

      <div class="form-group">
        <label class="form-label">{{ t('configDrawer.agentsPerTurn') }}</label>
        <input type="number" min="1" max="7" class="form-input"
          :value="modelValue.agents_per_turn ?? 3"
          @input="update('agents_per_turn', parseInt($event.target.value))" />
      </div>

      <!-- Moderator Section -->
      <div class="section-title">{{ t('configDrawer.moderator') }}</div>

      <div class="form-group">
        <label class="form-label">{{ t('configDrawer.moderatorName') }}</label>
        <input class="form-input"
          :value="modelValue.moderator_name ?? 'Moderator'"
          @input="update('moderator_name', $event.target.value)" />
      </div>

      <div class="form-group">
        <label class="form-label">{{ t('configDrawer.moderatorTitle') }}</label>
        <input class="form-input"
          :placeholder="t('configDrawer.moderatorTitlePlaceholder')"
          :value="modelValue.moderator_title ?? ''"
          @input="update('moderator_title', $event.target.value)" />
      </div>

      <div class="form-group">
        <label class="form-label">{{ t('configDrawer.mandate') }}</label>
        <textarea class="form-textarea"
          :placeholder="t('configDrawer.mandatePlaceholder')"
          :value="modelValue.moderator_mandate ?? ''"
          @input="update('moderator_mandate', $event.target.value)"></textarea>
      </div>

      <div class="form-group">
        <label class="form-label">{{ t('configDrawer.moderatorStyle') }}</label>
        <select class="form-select"
          :value="modelValue.moderator_style ?? 'neutral'"
          @change="update('moderator_style', $event.target.value)">
          <option value="neutral">{{ t('configDrawer.neutral') }}</option>
          <option value="challenging">{{ t('configDrawer.challenging') }}</option>
          <option value="facilitative">{{ t('configDrawer.facilitative') }}</option>
          <option value="socratic">{{ t('configDrawer.socratic') }}</option>
          <option value="devil's_advocate">{{ t('configDrawer.devilsAdvocate') }}</option>
        </select>
      </div>

      <div class="form-group">
        <label class="form-label">{{ t('configDrawer.customPersona') }}</label>
        <textarea class="form-textarea"
          :placeholder="t('configDrawer.customPersonaPlaceholder')"
          :value="modelValue.moderator_persona_prompt ?? ''"
          @input="update('moderator_persona_prompt', $event.target.value)"></textarea>
      </div>

      <!-- General Settings -->
      <div class="section-title">{{ t('configDrawer.general') }}</div>

      <div class="form-group">
        <label class="form-label form-label--checkbox">
          <input type="checkbox"
            :checked="modelValue.anti_groupthink ?? true"
            @change="update('anti_groupthink', $event.target.checked)"
            style="width: auto;" />
          {{ t('configDrawer.antiGroupthink') }}
        </label>
      </div>

      <div class="form-group">
        <label class="form-label">{{ t('configDrawer.devilsAdvocateRound') }}</label>
        <input type="number" min="0" max="10" class="form-input"
          :value="modelValue.devil_advocate_round ?? 0"
          @input="update('devil_advocate_round', parseInt($event.target.value))" />
      </div>

      <div class="form-group">
        <label class="form-label" for="config-temperature">
          {{ t('configDrawer.globalTemperature') }}
          <span class="temp-badge" aria-live="polite">{{ (modelValue.temperature_override ?? 0.7).toFixed(2) }}</span>
        </label>
        <input
          id="config-temperature"
          type="range" min="0" max="1.5" step="0.05"
          :value="modelValue.temperature_override ?? 0.7"
          :aria-valuenow="modelValue.temperature_override ?? 0.7"
          aria-valuemin="0" aria-valuemax="1.5"
          @input="update('temperature_override', parseFloat($event.target.value))"
          class="temp-slider"
        />
      </div>

      <div class="form-group">
        <label class="form-label">{{ t('configDrawer.contextWindowStrategy') }}</label>
        <select class="form-select"
          :value="modelValue.context_window_strategy ?? 'last_2_rounds'"
          @change="update('context_window_strategy', $event.target.value)">
          <option value="full">{{ t('configDrawer.full') }}</option>
          <option value="last_2_rounds">{{ t('configDrawer.last2Rounds') }}</option>
          <option value="synthesis_only">{{ t('configDrawer.synthesisOnly') }}</option>
        </select>
      </div>

      <!-- Whisper Channels (CR-011) — only shown when feature flag is on -->
      <template v-if="featureFlags.private_threads">
        <div class="section-title">{{ t('configDrawer.whisperChannels') }}</div>

        <div class="form-group">
          <label class="form-label">{{ t('configDrawer.threadLimit') }}</label>
          <input type="number" min="1" max="20" class="form-input"
            :value="modelValue.private_thread_limit ?? 3"
            @input="update('private_thread_limit', parseInt($event.target.value))" />
        </div>

        <div class="form-group">
          <label class="form-label">{{ t('configDrawer.maxExchanges') }}</label>
          <input type="number" min="1" max="10" class="form-input"
            :value="modelValue.private_thread_depth ?? 2"
            @input="update('private_thread_depth', parseInt($event.target.value))" />
        </div>

        <div class="form-group">
          <label class="form-label">{{ t('configDrawer.quotaMode') }}</label>
          <select class="form-select"
            :value="modelValue.private_thread_quota_mode ?? 'fixed'"
            @change="update('private_thread_quota_mode', $event.target.value)">
            <option value="fixed">{{ t('configDrawer.fixedQuota') }}</option>
            <option value="power_proportional">{{ t('configDrawer.powerProportional') }}</option>
          </select>
        </div>
      </template>

      <button class="btn btn-primary drawer-apply-btn" @click="emit('close')">{{ t('configDrawer.apply') }}</button>
    </div>
  </div>
</template>

<style scoped>
@keyframes slide-in-right {
  from { transform: translateX(100%); opacity: 0; }
  to   { transform: translateX(0);    opacity: 1; }
}

.drawer-overlay {
  position: fixed;
  inset: 0;
  z-index: 200;
  backdrop-filter: blur(4px);
  animation: fade-in 200ms ease;
}

.drawer-panel {
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  width: 360px;
  background: var(--surface);
  border-left: 1px solid var(--border);
  padding: 28px;
  overflow-y: auto;
  box-shadow: var(--shadow-xl);
  border-radius: var(--radius-lg) 0 0 var(--radius-lg);
  animation: slide-in-right 200ms ease;
}

.drawer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-6);
}

.drawer-title {
  font-size: 16px;
}

.drawer-close-btn {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-full);
  border: 1px solid var(--border);
  background: none;
  color: var(--text-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  transition: background var(--transition-fast), color var(--transition-fast);
}
.drawer-close-btn:hover {
  background: var(--surface-hover);
  color: var(--text);
}

.form-group {
  margin-bottom: var(--space-4);
}

.form-label--checkbox {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  text-transform: none;
  font-size: 13px;
  cursor: pointer;
}

.temp-slider {
  width: 100%;
  margin-top: var(--space-2);
}

.temp-badge {
  display: inline-block;
  background: var(--surface-alt);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-size: 11px;
  color: var(--text-muted);
  margin-top: var(--space-1);
}

.drawer-apply-btn {
  width: 100%;
  margin-top: var(--space-4);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-sm);
}
</style>
