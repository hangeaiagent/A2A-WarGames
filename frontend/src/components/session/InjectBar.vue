<script setup>
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSTT } from '../../composables/useSTT'

const { t } = useI18n()

const emit = defineEmits(['inject'])
const text = ref('')
const asModerator = ref(false)

const { isRecording, transcript, isEnabled: sttEnabled, toggleRecording } = useSTT()

watch(transcript, (val) => {
  if (val) text.value = val
})

function send() {
  if (!text.value.trim()) return
  emit('inject', text.value, asModerator.value)
  text.value = ''
}
</script>

<template>
  <div class="inject-bar">
    <label class="moderator-label">
      <input type="checkbox" v-model="asModerator" class="moderator-checkbox" />
      {{ t('injectBar.asModerator') }}
    </label>
    <textarea
      class="form-input inject-input inject-textarea"
      :placeholder="t('injectBar.placeholder')"
      v-model="text"
      rows="1"
      @keydown.enter.exact.prevent="send"
    />
    <button
      v-if="sttEnabled()"
      class="btn-mic"
      :class="{ recording: isRecording }"
      :title="isRecording ? t('injectBar.stopRecording') : t('injectBar.speak')"
      @click="toggleRecording"
    >
      {{ isRecording ? '⏺' : '🎤' }}
    </button>
    <button class="btn btn-primary inject-send-btn" @click="send">
      {{ t('injectBar.inject') }} →
    </button>
  </div>
</template>

<style scoped>
.inject-bar {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-2);
  align-items: center;
  flex-shrink: 0;
  background: var(--surface);
  padding: var(--space-3);
  border-radius: var(--radius);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
}

.moderator-label {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: 12px;
  color: var(--text-muted);
  white-space: nowrap;
  cursor: pointer;
}

.moderator-checkbox {
  width: auto;
}

.inject-input {
  flex: 1;
  border-radius: var(--radius-sm);
}

.inject-textarea {
  resize: none;
  min-height: 36px;
  max-height: 120px;
  overflow-y: auto;
  line-height: 1.5;
  padding-top: 8px;
  padding-bottom: 8px;
}

.inject-send-btn {
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-4);
  white-space: nowrap;
}

.btn-mic {
  padding: var(--space-2) var(--space-2);
  border: 1px solid var(--border);
  background: none;
  border-radius: var(--radius-full);
  cursor: pointer;
  font-size: 1.1rem;
  color: var(--text-muted);
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: border-color var(--transition-fast), color var(--transition-fast), background var(--transition-fast);
  flex-shrink: 0;
}
.btn-mic:hover {
  background: var(--surface-hover);
  color: var(--text);
  border-color: var(--border-hover);
}
.btn-mic.recording {
  border-color: var(--danger);
  color: var(--danger);
  animation: pulse 1s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.5; }
}
</style>
