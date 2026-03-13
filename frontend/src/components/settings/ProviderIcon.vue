<script setup>
import { computed } from 'vue'

const props = defineProps({
  provider: { type: String, required: true },
  size: { type: String, default: '20px' },
})

// Import all provider icons
const icons = import.meta.glob('../../assets/icons/providers/*.svg', { eager: true, query: '?url', import: 'default' })

const iconSrc = computed(() => {
  // Match provider id to svg file
  const key = Object.keys(icons).find(k => k.includes(`/${props.provider}.svg`))
  return key ? icons[key] : icons[Object.keys(icons).find(k => k.includes('/custom.svg'))] || ''
})
</script>

<template>
  <img :src="iconSrc" :alt="provider" :style="{ width: size, height: size }" class="provider-icon" />
</template>

<style scoped>
.provider-icon {
  display: inline-block;
  flex-shrink: 0;
  /* Make icon inherit text color in dark mode */
  filter: brightness(0) invert(1);
  opacity: 0.85;
}

/* For light theme, don't invert */
:root[data-theme="light"] .provider-icon {
  filter: brightness(0);
  opacity: 0.7;
}
</style>
