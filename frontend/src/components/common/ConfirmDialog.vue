<script setup>
import { onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

defineProps({ message: String })
const emit = defineEmits(['confirm', 'cancel'])

// Unique id per instance so multiple dialogs don't share the same aria-labelledby target
const dialogId = `confirm-dialog-${Math.random().toString(36).slice(2)}`

function onKeydown(e) {
  if (e.key === 'Escape') emit('cancel')
}

onMounted(() => document.addEventListener('keydown', onKeydown))
onUnmounted(() => document.removeEventListener('keydown', onKeydown))
</script>

<template>
  <Teleport to="body">
    <div class="modal-overlay" @click.self="emit('cancel')">
      <div
        class="modal"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="dialogId"
        style="width: 380px; text-align: center;"
      >
        <div :id="dialogId" class="modal-title">{{ t('common.confirm') }}</div>
        <p style="color: var(--text-muted); margin-bottom: 20px;">{{ message }}</p>
        <div class="modal-actions" style="justify-content: center;">
          <button class="btn btn-ghost" @click="emit('cancel')">{{ t('common.cancel') }}</button>
          <button class="btn btn-danger" @click="emit('confirm')">{{ t('common.confirm') }}</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
