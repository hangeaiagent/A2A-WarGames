<script setup>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import Spinner from '../common/Spinner.vue'

const { t } = useI18n({ useScope: 'global' })

defineProps({
  modelValue: { type: String, default: '' },
  placeholder: { type: String, default: 'API key...' },
  verified: { type: Boolean, default: false },
  testing: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'test'])

const visible = ref(false)

function toggleVisibility() {
  visible.value = !visible.value
}
</script>

<template>
  <div class="api-key-input">
    <div class="input-row">
      <div class="input-wrapper">
        <input
          :type="visible ? 'text' : 'password'"
          class="form-input key-input"
          :value="modelValue"
          :placeholder="placeholder"
          @input="emit('update:modelValue', $event.target.value)"
          autocomplete="off"
        />
        <button
          type="button"
          class="visibility-toggle"
          @click="toggleVisibility"
          :title="visible ? 'Hide' : 'Show'"
          :aria-label="visible ? 'Hide API key' : 'Show API key'"
        >
          <span v-if="visible" class="eye-icon">&#x1F441;</span>
          <span v-else class="eye-icon">&#x1F441;&#xFE0F;&#x200D;&#x1F5E8;&#xFE0F;</span>
        </button>
        <span v-if="verified && !testing" class="status-icon verified" :title="t('settings.providers.verified')">&#x2714;</span>
        <span v-else-if="modelValue && !testing" class="status-icon unverified" :title="t('settings.providers.notConfigured')">&#x26A0;</span>
      </div>
      <button
        type="button"
        class="btn btn-ghost test-btn"
        :disabled="!modelValue || testing"
        @click="emit('test')"
        :title="t('settings.providers.testConnection')"
      >
        <Spinner v-if="testing" size="14px" />
        <span v-else>{{ t('settings.providers.testConnection') }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.api-key-input {
  width: 100%;
}

.input-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.input-wrapper {
  flex: 1;
  position: relative;
  display: flex;
  align-items: center;
}

.key-input {
  width: 100%;
  padding-right: 60px;
  font-family: var(--font-mono);
  font-size: 12px;
}

.visibility-toggle {
  position: absolute;
  right: 30px;
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px;
  opacity: 0.6;
  transition: opacity var(--transition-fast);
  line-height: 1;
}

.visibility-toggle:hover {
  opacity: 1;
}

.eye-icon {
  font-size: 14px;
}

.status-icon {
  position: absolute;
  right: 8px;
  font-size: 14px;
  line-height: 1;
}

.status-icon.verified {
  color: var(--provider-verified);
}

.status-icon.unverified {
  color: var(--provider-unverified);
}

.test-btn {
  flex-shrink: 0;
  white-space: nowrap;
  font-size: 12px;
  padding: 6px 12px;
}

@media (max-width: 640px) {
  .input-row {
    flex-direction: column;
    align-items: stretch;
  }

  .test-btn {
    width: 100%;
  }
}
</style>
