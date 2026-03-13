<script setup>
defineProps({
  width: { type: String, default: '100%' },
  height: { type: String, default: '14px' },
  rounded: { type: Boolean, default: false },
  count: { type: Number, default: 1 },
})
</script>

<template>
  <div class="skeleton-wrapper">
    <div
      v-for="i in count"
      :key="i"
      class="skeleton-bar"
      :style="{
        width: i === count && count > 1 ? '70%' : width,
        height,
        borderRadius: rounded ? 'var(--radius-full)' : 'var(--radius-xs)',
      }"
    />
  </div>
</template>

<style scoped>
.skeleton-wrapper {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.skeleton-bar {
  background: linear-gradient(90deg, var(--border) 25%, var(--surface-hover) 50%, var(--border) 75%);
  background-size: 200% 100%;
  animation: skeleton-shimmer 1.5s infinite ease-in-out;
}
@keyframes skeleton-shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
</style>
