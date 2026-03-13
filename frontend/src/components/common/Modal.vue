<script setup>
import { onMounted, onUnmounted } from 'vue'

const props = defineProps({
  title: String,
  width: { type: [Number, String], default: 520 },
})
const emit = defineEmits(['close'])

const titleId = `modal-title-${Math.random().toString(36).slice(2)}`

function onKeydown(e) {
  if (e.key === 'Escape') emit('close')
}

onMounted(() => document.addEventListener('keydown', onKeydown))
onUnmounted(() => document.removeEventListener('keydown', onKeydown))
</script>

<template>
  <Teleport to="body">
    <div class="modal-overlay" @click.self="emit('close')">
      <div
        class="modal"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="title ? titleId : undefined"
        :style="{ width: typeof width === 'number' ? width + 'px' : width }"
      >
        <div v-if="title" :id="titleId" class="modal-title">{{ title }}</div>
        <slot />
      </div>
    </div>
  </Teleport>
</template>
