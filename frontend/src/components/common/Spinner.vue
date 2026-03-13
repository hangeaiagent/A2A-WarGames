<script setup>
import { computed } from 'vue'
import { VueSpinnerClip, VueSpinnerRing } from 'vue3-spinners'

const props = defineProps({
  /** 'clip' (default, inline-friendly) | 'ring' (3D dual-orbit, for large loading states) */
  variant: { type: String, default: 'clip' },
  size: { type: [String, Number], default: '20px' },
  color: { type: String, default: 'var(--accent)' },
})

const isRing = computed(() => props.variant === 'ring')
</script>

<template>
  <span class="spinner-wrap" role="status" aria-label="Loading">
    <VueSpinnerRing v-if="isRing" :size="size" :color="color" />
    <VueSpinnerClip v-else :size="size" :color="color" />
    <span class="sr-only">Loading...</span>
  </span>
</template>

<style scoped>
.spinner-wrap {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  vertical-align: middle;
  line-height: 0;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  border: 0;
}
</style>
