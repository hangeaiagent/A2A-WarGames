<script setup>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps({ modelValue: Object })
const emit = defineEmits(['update:modelValue'])

const collapsed = ref(true)

function update(key, val) {
  emit('update:modelValue', { ...props.modelValue, [key]: val })
}
</script>

<template>
  <div style="margin-top: 8px;">
    <button
      type="button"
      class="btn btn-ghost"
      style="width: 100%; text-align: left; font-size: 12px; font-weight: 700; padding: 8px 12px;"
      @click="collapsed = !collapsed"
    >
      {{ collapsed ? '▶' : '▼' }} {{ t('simParams.title') }}
    </button>

    <div v-if="!collapsed" style="padding: 16px; border: 1px solid var(--border); border-top: none; border-radius: 0 0 var(--radius) var(--radius);">
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
        <div class="form-group">
          <label class="form-label">{{ t('simParams.maxTurnsPerRound') }}</label>
          <input
            type="number" min="1" max="10" class="form-input"
            :value="modelValue.max_turns_per_round ?? 3"
            @input="update('max_turns_per_round', parseInt($event.target.value))"
          />
        </div>

        <div class="form-group">
          <label class="form-label">{{ t('simParams.speakingPriority') }}</label>
          <input
            type="range" min="0" max="2" step="0.1"
            :value="modelValue.speaking_priority ?? 1.0"
            @input="update('speaking_priority', parseFloat($event.target.value))"
            style="width: 100%; margin-top: 8px;"
          />
          <div style="font-size: 11px; color: var(--text-muted);">{{ (modelValue.speaking_priority ?? 1.0).toFixed(1) }}</div>
        </div>

        <div class="form-group">
          <label class="form-label">{{ t('simParams.tokenBudget') }}</label>
          <input
            type="range" min="128" max="2048" step="128"
            :value="modelValue.max_tokens ?? 1024"
            @input="update('max_tokens', parseInt($event.target.value))"
            style="width: 100%; margin-top: 8px;"
          />
          <div style="font-size: 11px; color: var(--text-muted);">{{ t('simParams.tokens', { value: modelValue.max_tokens ?? 1024 }) }}</div>
        </div>

        <div class="form-group">
          <label class="form-label">{{ t('simParams.temperatureOverride') }}</label>
          <input
            type="range" min="0" max="1.5" step="0.05"
            :value="modelValue.temperature ?? 0.7"
            @input="update('temperature', parseFloat($event.target.value))"
            style="width: 100%; margin-top: 8px;"
          />
          <div style="font-size: 11px; color: var(--text-muted);">{{ (modelValue.temperature ?? 0.7).toFixed(2) }}</div>
        </div>
      </div>

      <div class="form-group" style="margin-bottom: 0;">
        <label class="form-label" style="display: flex; align-items: center; gap: 10px; cursor: pointer; text-transform: none; font-size: 13px;">
          <input
            type="checkbox"
            :checked="modelValue.is_silenced ?? false"
            @change="update('is_silenced', $event.target.checked)"
            style="width: auto;"
          />
          {{ t('simParams.silenced') }}
        </label>
      </div>
    </div>
  </div>
</template>
